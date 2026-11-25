"""Organizations, memberships, RBAC enforcement and audit logging (HTTP level)."""

from __future__ import annotations

import uuid

import pytest

from tests.integration.api.conftest import Actor, Api

pytestmark = pytest.mark.integration


def _join(api: Api, owner: Actor, role: str) -> Actor:
    """A verified user who joined ``owner``'s org with ``role`` through a real invitation."""
    newcomer = api.signup()
    invite = owner.post(
        f"/orgs/{owner.org_id}/invitations", {"email": newcomer.email, "role": role}
    )
    assert invite.status_code == 201, invite.text
    token = api.mailbox.last_token(newcomer.email, path="invite")
    accepted = newcomer.post("/invitations/accept", {"token": token})
    assert accepted.status_code == 200, accepted.text
    newcomer.org_id = owner.org_id
    return newcomer


def _membership_id(owner: Actor, user: Actor) -> str:
    members = owner.get(f"/orgs/{owner.org_id}/members").json()["data"]
    return str(next(m["id"] for m in members if m["user"]["id"] == user.user_id))


def _audit_actions(actor: Actor) -> list[str]:
    return [
        e["action"] for e in actor.get(f"/orgs/{actor.org_id}/audit-logs?limit=100").json()["data"]
    ]


# ------------------------------------------------------------------------------ orgs


def test_verified_user_creates_org_and_becomes_owner(api: Api) -> None:
    user = api.signup()

    response = user.post("/orgs", {"name": "Second Org"})

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "owner"
    assert "org:transfer" in body["permissions"]
    assert {o["name"] for o in user.get("/orgs").json()["data"]} >= {"Second Org"}


def test_client_cannot_choose_org_id_or_status_on_create(api: Api) -> None:
    user = api.signup()

    for extra in (
        {"id": str(uuid.uuid4())},
        {"org_id": str(uuid.uuid4())},
        {"status": "suspended"},
    ):
        assert user.post("/orgs", {"name": "X", **extra}).status_code == 422


def test_list_orgs_returns_only_orgs_the_user_belongs_to(api: Api) -> None:
    alice, bob = api.signup(org_name="Alice Co"), api.signup(org_name="Bob Co")

    names = {o["name"] for o in alice.get("/orgs").json()["data"]}

    assert names == {"Alice Co"}
    assert bob.org_id not in {o["id"] for o in alice.get("/orgs").json()["data"]}


def test_owner_and_admin_can_rename_org_but_agent_and_viewer_cannot(api: Api) -> None:
    owner = api.signup()
    admin, agent, viewer = (_join(api, owner, r) for r in ("admin", "agent", "viewer"))
    path = f"/orgs/{owner.org_id}"

    assert owner.patch(path, {"name": "Renamed"}).status_code == 200
    assert admin.patch(path, {"name": "Renamed by admin"}).status_code == 200
    assert agent.patch(path, {"name": "Nope"}).status_code == 403
    assert viewer.patch(path, {"name": "Nope"}).status_code == 403
    assert owner.get(path).json()["name"] == "Renamed by admin"


def test_org_update_rejects_unknown_and_privileged_fields(api: Api) -> None:
    owner = api.signup()
    path = f"/orgs/{owner.org_id}"

    for body in ({"status": "active"}, {"slug": "x"}, {"settings": {"billing": 1}}, {"id": "x"}):
        assert owner.patch(path, body).status_code == 422


def test_org_settings_are_merged_and_validated(api: Api) -> None:
    owner = api.signup()
    path = f"/orgs/{owner.org_id}"

    ok = owner.patch(path, {"settings": {"conversation_retention_days": 30}})
    bad = owner.patch(path, {"settings": {"conversation_retention_days": 0}})

    assert ok.json()["settings"] == {"conversation_retention_days": 30}
    assert bad.status_code == 422


# --------------------------------------------------------------------------- members


def test_every_role_can_list_members(api: Api) -> None:
    owner = api.signup()
    others = [_join(api, owner, r) for r in ("admin", "agent", "viewer")]

    for actor in (owner, *others):
        response = actor.get(f"/orgs/{owner.org_id}/members")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 4


def test_agent_cannot_perform_owner_only_or_admin_actions(api: Api) -> None:
    owner = api.signup()
    admin = _join(api, owner, "admin")
    agent = _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"
    admin_membership = _membership_id(owner, admin)

    attempts = {
        "transfer": agent.post(
            f"{base}/transfer-ownership",
            {"new_owner_user_id": admin.user_id, "password": agent.password},
        ),
        "invite": agent.post(f"{base}/invitations", {"email": "x@example.com", "role": "viewer"}),
        "list invites": agent.get(f"{base}/invitations"),
        "change role": agent.patch(f"{base}/members/{admin_membership}", {"role": "viewer"}),
        "remove member": agent.delete(f"{base}/members/{admin_membership}"),
        "audit": agent.get(f"{base}/audit-logs"),
        "rename": agent.patch(base, {"name": "x"}),
    }

    assert {k: v.status_code for k, v in attempts.items()} == dict.fromkeys(attempts, 403)
    assert owner.get(f"{base}/members").json()["data"][0]["role"] == "owner"


def test_admin_manages_agents_but_cannot_touch_or_create_owners(api: Api) -> None:
    owner = api.signup()
    admin, agent = _join(api, owner, "admin"), _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"
    owner_membership = _membership_id(owner, owner)

    promote_agent = admin.patch(
        f"{base}/members/{_membership_id(owner, agent)}", {"role": "viewer"}
    )
    promote_to_owner = admin.patch(
        f"{base}/members/{_membership_id(owner, agent)}", {"role": "owner"}
    )
    demote_owner = admin.patch(f"{base}/members/{owner_membership}", {"role": "viewer"})
    remove_owner = admin.delete(f"{base}/members/{owner_membership}")

    assert promote_agent.status_code == 200
    assert promote_agent.json()["role"] == "viewer"
    assert promote_to_owner.status_code == 422  # "owner" is not an assignable role
    assert demote_owner.status_code == 403
    assert remove_owner.status_code == 403
    assert owner.get(f"{base}/members").status_code == 200


def test_member_cannot_change_their_own_role(api: Api) -> None:
    owner = api.signup()
    admin = _join(api, owner, "admin")
    own_membership = _membership_id(owner, admin)

    response = admin.patch(f"/orgs/{owner.org_id}/members/{own_membership}", {"role": "admin"})

    assert response.status_code == 403


def test_role_change_takes_effect_on_the_very_next_request(api: Api) -> None:
    owner = api.signup()
    admin = _join(api, owner, "admin")
    path = f"/orgs/{owner.org_id}"
    assert admin.patch(path, {"name": "As admin"}).status_code == 200

    owner.patch(f"{path}/members/{_membership_id(owner, admin)}", {"role": "viewer"})

    assert admin.patch(path, {"name": "As viewer"}).status_code == 403
    assert admin.get(path).status_code == 200  # still a member, now read-only


def test_revoked_membership_blocks_access_immediately(api: Api) -> None:
    owner = api.signup()
    agent = _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"
    assert agent.get(base).status_code == 200  # warm: session is valid and cached nowhere

    removed = owner.delete(f"{base}/members/{_membership_id(owner, agent)}")

    assert removed.status_code == 204
    for path in (base, f"{base}/members", f"{base}/invitations"):
        assert agent.get(path).status_code == 404  # same session, instantly denied
    assert agent.get("/me").status_code == 200  # the account itself is unaffected
    assert owner.org_id not in {o["id"] for o in agent.get("/orgs").json()["data"]}


def test_removing_a_member_keeps_content_they_authored_in_the_audit_log(api: Api) -> None:
    owner = api.signup()
    admin = _join(api, owner, "admin")
    admin.patch(f"/orgs/{owner.org_id}", {"name": "Admin was here"})

    owner.delete(f"/orgs/{owner.org_id}/members/{_membership_id(owner, admin)}")

    assert "org.updated" in _audit_actions(owner)


def test_last_owner_cannot_leave_or_be_removed(api: Api) -> None:
    owner = api.signup()
    base = f"/orgs/{owner.org_id}"

    leave = owner.delete(f"{base}/members/{_membership_id(owner, owner)}")

    assert leave.status_code == 409
    assert leave.json()["code"] == "last_owner"
    assert owner.get(base).status_code == 200


def test_non_owner_members_can_leave(api: Api) -> None:
    owner = api.signup()
    agent = _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"

    left = agent.delete(f"{base}/members/{_membership_id(owner, agent)}")

    assert left.status_code == 204
    assert agent.get(base).status_code == 404
    assert "member.left" in _audit_actions(owner)


def test_viewer_cannot_remove_another_member(api: Api) -> None:
    owner = api.signup()
    viewer, agent = _join(api, owner, "viewer"), _join(api, owner, "agent")

    response = viewer.delete(f"/orgs/{owner.org_id}/members/{_membership_id(owner, agent)}")

    assert response.status_code == 403


def test_ownership_transfer_requires_password_and_an_admin_target(api: Api) -> None:
    owner = api.signup()
    admin, agent = _join(api, owner, "admin"), _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"

    wrong_pw = owner.post(
        f"{base}/transfer-ownership",
        {"new_owner_user_id": admin.user_id, "password": "nope nope nope"},
    )
    to_agent = owner.post(
        f"{base}/transfer-ownership",
        {"new_owner_user_id": agent.user_id, "password": owner.password},
    )
    to_self = owner.post(
        f"{base}/transfer-ownership",
        {"new_owner_user_id": owner.user_id, "password": owner.password},
    )
    ok = owner.post(
        f"{base}/transfer-ownership",
        {"new_owner_user_id": admin.user_id, "password": owner.password},
    )

    assert (wrong_pw.status_code, to_agent.status_code, to_self.status_code) == (400, 409, 403)
    assert ok.status_code == 200
    roles = {m["user"]["id"]: m["role"] for m in admin.get(f"{base}/members").json()["data"]}
    assert roles[admin.user_id] == "owner"
    assert roles[owner.user_id] == "admin"
    assert "org.ownership_transferred" in _audit_actions(admin)


def test_transfer_to_a_non_member_is_not_found(api: Api) -> None:
    owner, stranger = api.signup(), api.signup()

    response = owner.post(
        f"/orgs/{owner.org_id}/transfer-ownership",
        {"new_owner_user_id": stranger.user_id, "password": owner.password},
    )

    assert response.status_code == 404


# ----------------------------------------------------------------------------- audit


def test_sensitive_actions_each_write_one_audit_row_with_actor_and_target(api: Api) -> None:
    owner = api.signup()
    agent = _join(api, owner, "agent")
    base = f"/orgs/{owner.org_id}"
    membership = _membership_id(owner, agent)

    owner.patch(f"{base}/members/{membership}", {"role": "viewer"})
    owner.delete(f"{base}/members/{membership}")
    pending = owner.post(
        f"{base}/invitations", {"email": "later@example.com", "role": "viewer"}
    ).json()
    owner.delete(f"{base}/invitations/{pending['id']}")

    logs = owner.get(f"{base}/audit-logs?limit=100").json()["data"]
    by_action = {e["action"]: e for e in logs}
    for action in (
        "org.created",
        "member.invited",
        "invitation.accepted",
        "member.role_changed",
        "member.removed",
        "invitation.revoked",
    ):
        assert action in by_action, action
        assert [e["action"] for e in logs].count(action) == (2 if action == "member.invited" else 1)
    changed = by_action["member.role_changed"]
    assert changed["actor"]["id"] == owner.user_id
    assert changed["target_id"] == membership
    assert changed["metadata"]["from"] == "agent"
    assert changed["metadata"]["to"] == "viewer"
    assert changed["request_id"]


def test_audit_log_never_contains_secrets(api: Api) -> None:
    owner = api.signup()
    owner.post(
        f"/orgs/{owner.org_id}/invitations", {"email": "secret@example.com", "role": "viewer"}
    )
    token = api.mailbox.last_token("secret@example.com", path="invite")

    dump = owner.get(f"/orgs/{owner.org_id}/audit-logs?limit=100").text

    assert token not in dump
    assert owner.password not in dump
    assert "token_hash" not in dump


def test_audit_log_is_paginated_newest_first(api: Api) -> None:
    owner = api.signup()
    for i in range(3):
        owner.patch(f"/orgs/{owner.org_id}", {"name": f"Name {i}"})
    base = f"/orgs/{owner.org_id}/audit-logs"

    page1 = owner.get(f"{base}?limit=2").json()
    page2 = owner.get(f"{base}?limit=2&cursor={page1['next_cursor']}").json()

    assert len(page1["data"]) == 2
    assert page1["has_more"] is True
    assert page1["data"][0]["action"] == "org.updated"
    assert page2["data"][0]["id"] != page1["data"][1]["id"]
    assert owner.get(f"{base}?cursor=garbage").status_code == 400


def test_audit_rows_are_append_only_in_the_database(api: Api) -> None:
    owner = api.signup()

    rows = api.sql("SELECT count(*) FROM audit_logs WHERE org_id = :o", o=owner.org_id)[0][0]

    assert rows >= 1  # runtime-role immutability itself is asserted in tenancy/test_rls.py
