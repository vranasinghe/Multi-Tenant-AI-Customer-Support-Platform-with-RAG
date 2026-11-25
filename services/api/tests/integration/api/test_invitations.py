"""Invitations: expiring, single-use, email-bound tokens."""

from __future__ import annotations

import uuid

import pytest

from tests.integration.api.conftest import Actor, Api

pytestmark = pytest.mark.integration


def _invite(owner: Actor, email: str, role: str = "agent"):  # type: ignore[no-untyped-def]
    return owner.post(f"/orgs/{owner.org_id}/invitations", {"email": email, "role": role})


def test_invitation_email_carries_a_link_and_only_a_hash_is_stored(api: Api) -> None:
    owner = api.signup()
    email = f"new-{uuid.uuid4().hex[:8]}@example.com"

    response = _invite(owner, email, "agent")

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    token = api.mailbox.last_token(email, path="invite")
    hashes = [bytes(r[0]) for r in api.sql("SELECT token_hash FROM invitations")]
    assert token.encode() not in hashes
    assert all(len(h) == 32 for h in hashes)
    assert owner.org_id not in api.mailbox.to(email)[0].text  # no raw ids in the mail body


def test_invitation_expires_in_seven_days(api: Api) -> None:
    owner = api.signup()
    email = f"seven-{uuid.uuid4().hex[:8]}@example.com"
    _invite(owner, email)

    (days,) = api.sql(
        "SELECT round(extract(epoch FROM expires_at - created_at) / 86400) FROM invitations "
        "WHERE email = :e",
        e=email,
    )[0]

    assert days == 7


def test_invitee_accepts_and_gets_the_invited_role(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    _invite(owner, invitee.email, "viewer")
    token = api.mailbox.last_token(invitee.email, path="invite")

    accepted = invitee.post("/invitations/accept", {"token": token})

    assert accepted.status_code == 200
    assert accepted.json() == {
        "id": owner.org_id,
        "name": accepted.json()["name"],
        "role": "viewer",
    }
    assert invitee.get(f"/orgs/{owner.org_id}").json()["role"] == "viewer"
    assert owner.org_id in {o["id"] for o in invitee.get("/orgs").json()["data"]}


def test_invitation_token_cannot_be_reused(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    _invite(owner, invitee.email)
    token = api.mailbox.last_token(invitee.email, path="invite")
    assert invitee.post("/invitations/accept", {"token": token}).status_code == 200
    invitee.delete(
        f"/orgs/{owner.org_id}/members/{owner.get(f'/orgs/{owner.org_id}/members').json()['data'][1]['id']}"
    )

    replay = invitee.post("/invitations/accept", {"token": token})

    assert replay.status_code == 400
    assert replay.json()["code"] == "invalid_token"
    assert invitee.get(f"/orgs/{owner.org_id}").status_code == 404  # still not a member


def test_expired_invitation_cannot_be_accepted_or_looked_up(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    _invite(owner, invitee.email)
    token = api.mailbox.last_token(invitee.email, path="invite")
    api.sql(
        "UPDATE invitations SET expires_at = now() - interval '1 second' WHERE email = :e",
        e=invitee.email,
    )

    assert invitee.post("/invitations/accept", {"token": token}).status_code == 400
    assert api.anonymous().get(f"/invitations/lookup?token={token}", cookie=None).status_code == 400


def test_invitation_bound_to_one_email_cannot_be_accepted_by_another_account(api: Api) -> None:
    owner = api.signup()
    alice, bob = api.signup(), api.signup()
    _invite(owner, alice.email)
    token = api.mailbox.last_token(alice.email, path="invite")

    stolen = bob.post("/invitations/accept", {"token": token})
    legit = alice.post("/invitations/accept", {"token": token})

    assert stolen.status_code == 403  # AC1.5
    assert bob.get(f"/orgs/{owner.org_id}").status_code == 404
    assert legit.status_code == 200  # the failed attempt did not burn the token


def test_email_match_is_case_insensitive(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup(email=f"mixed-{uuid.uuid4().hex[:6]}@example.com")
    _invite(owner, invitee.email.upper())
    token = api.mailbox.last_token(invitee.email.upper(), path="invite")

    assert invitee.post("/invitations/accept", {"token": token}).status_code == 200


def test_unverified_user_cannot_accept(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup(verified=False)
    _invite(owner, invitee.email)
    token = api.mailbox.last_token(invitee.email, path="invite")

    response = invitee.post("/invitations/accept", {"token": token})

    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


def test_accepting_requires_authentication(api: Api) -> None:
    owner = api.signup()
    _invite(owner, "someone@example.com")
    token = api.mailbox.last_token("someone@example.com", path="invite")

    assert (
        api.anonymous().post("/invitations/accept", {"token": token}, cookie=None).status_code
        == 401
    )


def test_garbage_and_unknown_tokens_are_rejected(api: Api) -> None:
    user = api.signup()

    assert user.post("/invitations/accept", {"token": "x" * 43}).status_code == 400
    assert user.post("/invitations/accept", {"token": "short"}).status_code == 422


def test_lookup_is_public_and_masks_the_email(api: Api) -> None:
    owner = api.signup(name="Olivia Owner", org_name="Acme Lookup")
    _invite(owner, "private.person@example.com", "admin")
    token = api.mailbox.last_token("private.person@example.com", path="invite")

    response = api.anonymous().get(f"/invitations/lookup?token={token}", cookie=None)

    assert response.status_code == 200
    assert response.json() == {
        "org_name": "Acme Lookup",
        "inviter_name": "Olivia Owner",
        "role": "admin",
        "email_hint": "p***@example.com",
    }
    assert "private.person" not in response.text


def test_lookup_is_rate_limited(api: Api, api_settings) -> None:  # type: ignore[no-untyped-def]
    # Default limit is lifted for the suite; exercise the real limiter in a dedicated app.
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = api_settings.model_copy(update={"rate_limit_invite_lookup_per_minute": 3})
    with TestClient(
        create_app(settings, email_sender=api.mailbox), base_url="https://testserver"
    ) as c:
        codes = [
            c.get("/api/v1/invitations/lookup", params={"token": "x" * 43}).status_code
            for _ in range(5)
        ]

    assert codes == [400, 400, 400, 429, 429]


def test_cannot_invite_owner_or_unknown_role(api: Api) -> None:
    owner = api.signup()

    assert _invite(owner, "a@example.com", "owner").status_code == 422
    assert _invite(owner, "a@example.com", "superadmin").status_code == 422


def test_cannot_invite_existing_member_or_duplicate_pending(api: Api) -> None:
    owner = api.signup()
    member = api.signup()
    _invite(owner, member.email)
    member.post(
        "/invitations/accept", {"token": api.mailbox.last_token(member.email, path="invite")}
    )
    _invite(owner, "pending@example.com")

    already = _invite(owner, member.email)
    duplicate = _invite(owner, "pending@example.com")

    assert (already.status_code, already.json()["code"]) == (409, "already_member")
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "conflict")


def test_unverified_inviter_cannot_invite(api: Api) -> None:
    owner = api.signup(verified=False)

    response = _invite(owner, "x@example.com")

    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


def test_expired_pending_invite_can_be_reissued(api: Api) -> None:
    owner = api.signup()
    _invite(owner, "again@example.com")
    api.sql(
        "UPDATE invitations SET expires_at = now() - interval '1 day' WHERE email = :e",
        e="again@example.com",
    )

    assert _invite(owner, "again@example.com").status_code == 201


def test_resend_rotates_the_token_so_the_old_link_dies(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    created = _invite(owner, invitee.email).json()
    first = api.mailbox.last_token(invitee.email, path="invite")

    resent = owner.post(f"/orgs/{owner.org_id}/invitations/{created['id']}/resend")
    second = api.mailbox.last_token(invitee.email, path="invite")

    assert resent.status_code == 200
    assert first != second
    assert invitee.post("/invitations/accept", {"token": first}).status_code == 400
    assert invitee.post("/invitations/accept", {"token": second}).status_code == 200


def test_resend_revives_an_expired_invitation(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    created = _invite(owner, invitee.email).json()
    api.sql(
        "UPDATE invitations SET expires_at = now() - interval '1 day' WHERE email = :e",
        e=invitee.email,
    )

    owner.post(f"/orgs/{owner.org_id}/invitations/{created['id']}/resend")

    token = api.mailbox.last_token(invitee.email, path="invite")
    assert invitee.post("/invitations/accept", {"token": token}).status_code == 200


def test_revoked_invitation_cannot_be_accepted(api: Api) -> None:
    owner = api.signup()
    invitee = api.signup()
    created = _invite(owner, invitee.email).json()
    token = api.mailbox.last_token(invitee.email, path="invite")

    assert owner.delete(f"/orgs/{owner.org_id}/invitations/{created['id']}").status_code == 204

    assert invitee.post("/invitations/accept", {"token": token}).status_code == 400
    assert owner.get(f"/orgs/{owner.org_id}/invitations").json()["data"] == []


def test_admin_can_invite_admins_but_viewer_cannot_invite(api: Api) -> None:
    owner = api.signup()
    admin_user, viewer_user = api.signup(), api.signup()
    for user, role in ((admin_user, "admin"), (viewer_user, "viewer")):
        _invite(owner, user.email, role)
        user.post(
            "/invitations/accept", {"token": api.mailbox.last_token(user.email, path="invite")}
        )
        user.org_id = owner.org_id

    assert _invite(admin_user, "a1@example.com", "admin").status_code == 201
    assert _invite(admin_user, "a2@example.com", "owner").status_code == 422
    assert _invite(viewer_user, "a3@example.com", "viewer").status_code == 403


def test_accepting_the_same_token_twice_yields_exactly_one_membership(api: Api) -> None:
    """Back-to-back accepts: one wins, the other is rejected, one membership row exists."""
    owner = api.signup()
    invitee = api.signup()
    _invite(owner, invitee.email)
    token = api.mailbox.last_token(invitee.email, path="invite")

    first = invitee.post("/invitations/accept", {"token": token})
    second = invitee.post("/invitations/accept", {"token": token})

    assert sorted([first.status_code, second.status_code]) == [200, 400]
    count = api.sql(
        "SELECT count(*) FROM memberships WHERE org_id = :o AND user_id = :u",
        o=owner.org_id,
        u=invitee.user_id,
    )[0][0]
    assert count == 1
