"""Cross-tenant isolation through the HTTP API (docs/DATABASE.md §4.4, SECURITY.md §5, AC1.7).

A user of org A must never read, change or even detect resources of org B: every probe must look
exactly like a request for something that does not exist (404).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI

from tests.integration.api.conftest import Actor, Api
from tests.support.routes import fill_path, iter_api_routes

pytestmark = pytest.mark.integration


def _invite_into(api: Api, owner: Actor, user: Actor, role: str) -> None:
    owner.post(f"/orgs/{owner.org_id}/invitations", {"email": user.email, "role": role})
    token = api.mailbox.last_token(user.email, path="invite")
    assert user.post("/invitations/accept", {"token": token}).status_code == 200


def _two_tenants(api: Api) -> tuple[Actor, Actor]:
    return api.signup(org_name="Org A"), api.signup(org_name="Org B")


def test_user_a_cannot_access_user_b_organization(api: Api) -> None:
    a, b = _two_tenants(api)
    b_member = b.get(f"/orgs/{b.org_id}/members").json()["data"][0]["id"]
    b_invite = b.post(
        f"/orgs/{b.org_id}/invitations", {"email": "x@example.com", "role": "viewer"}
    ).json()["id"]
    base = f"/orgs/{b.org_id}"

    probes = {
        "get org": a.get(base),
        "patch org": a.patch(base, {"name": "pwned"}),
        "list members": a.get(f"{base}/members"),
        "change role": a.patch(f"{base}/members/{b_member}", {"role": "viewer"}),
        "remove member": a.delete(f"{base}/members/{b_member}"),
        "list invites": a.get(f"{base}/invitations"),
        "create invite": a.post(
            f"{base}/invitations", {"email": "evil@example.com", "role": "admin"}
        ),
        "resend invite": a.post(f"{base}/invitations/{b_invite}/resend"),
        "revoke invite": a.delete(f"{base}/invitations/{b_invite}"),
        "audit logs": a.get(f"{base}/audit-logs"),
        "transfer": a.post(
            f"{base}/transfer-ownership", {"new_owner_user_id": a.user_id, "password": a.password}
        ),
    }

    assert {name: r.status_code for name, r in probes.items()} == dict.fromkeys(probes, 404)
    bodies = {r.text for r in probes.values()}
    assert not any(b.org_id in body or "Org B" in body for body in bodies)


def test_other_orgs_members_and_invitations_are_untouched_after_attacks(api: Api) -> None:
    a, b = _two_tenants(api)
    b_member = b.get(f"/orgs/{b.org_id}/members").json()["data"][0]["id"]

    a.patch(f"/orgs/{b.org_id}/members/{b_member}", {"role": "viewer"})
    a.delete(f"/orgs/{b.org_id}/members/{b_member}")
    a.patch(f"/orgs/{b.org_id}", {"name": "pwned"})

    assert b.get(f"/orgs/{b.org_id}").json()["name"] == "Org B"
    assert b.get(f"/orgs/{b.org_id}/members").json()["data"][0]["role"] == "owner"


def test_membership_id_from_another_org_is_not_usable_under_my_org(api: Api) -> None:
    """IDOR: my org id in the URL, someone else's membership id as the resource."""
    a, b = _two_tenants(api)
    b_member = b.get(f"/orgs/{b.org_id}/members").json()["data"][0]["id"]

    changed = a.patch(f"/orgs/{a.org_id}/members/{b_member}", {"role": "viewer"})
    removed = a.delete(f"/orgs/{a.org_id}/members/{b_member}")

    assert (changed.status_code, removed.status_code) == (404, 404)
    assert b.get(f"/orgs/{b.org_id}/members").json()["data"][0]["role"] == "owner"


def test_invitation_id_from_another_org_is_not_usable_under_my_org(api: Api) -> None:
    a, b = _two_tenants(api)
    b_invite = b.post(
        f"/orgs/{b.org_id}/invitations", {"email": "x@example.com", "role": "viewer"}
    ).json()["id"]

    resend = a.post(f"/orgs/{a.org_id}/invitations/{b_invite}/resend")
    revoke = a.delete(f"/orgs/{a.org_id}/invitations/{b_invite}")

    assert (resend.status_code, revoke.status_code) == (404, 404)
    assert len(b.get(f"/orgs/{b.org_id}/invitations").json()["data"]) == 1


def test_nonexistent_org_looks_the_same_as_someone_elses_org(api: Api) -> None:
    a, b = _two_tenants(api)

    foreign = a.get(f"/orgs/{b.org_id}/members")
    missing = a.get(f"/orgs/{uuid.uuid4()}/members")

    assert foreign.status_code == missing.status_code == 404
    left, right = foreign.json(), missing.json()
    left.pop("request_id"), right.pop("request_id")
    assert left == right


def test_client_supplied_org_hints_are_ignored(api: Api) -> None:
    """Headers, query strings and bodies cannot redirect a request to another tenant."""
    a, b = _two_tenants(api)

    response = a.get(
        f"/orgs/{a.org_id}/members?org_id={b.org_id}",
        headers={"X-Org-Id": b.org_id, "X-Organization": b.org_id},
    )

    assert response.status_code == 200
    emails = {m["user"]["email"] for m in response.json()["data"]}
    assert emails == {a.email}
    assert a.patch(f"/orgs/{a.org_id}", {"org_id": b.org_id}).status_code == 422


def test_unauthenticated_requests_cannot_probe_for_orgs(api: Api) -> None:
    a, _ = _two_tenants(api)
    anon = api.anonymous()

    codes = {
        anon.get(f"/orgs/{a.org_id}", cookie=None).status_code,
        anon.get(f"/orgs/{uuid.uuid4()}", cookie=None).status_code,
    }

    assert codes == {401}  # identical for real and fake orgs: no existence oracle


def test_every_org_scoped_route_returns_404_to_a_non_member(app: FastAPI, api: Api) -> None:
    """Auto-discovered: no org-scoped route, present or future, may skip the membership check."""
    a, b = _two_tenants(api)
    routes = [r for r in iter_api_routes(app) if "/{org_id}" in r.path]
    assert len(routes) >= 10, "route discovery found suspiciously few org-scoped routes"

    failures: list[str] = []
    for route in routes:
        path = fill_path(route, org_id=b.org_id)
        for method in route.sendable_methods:
            options: dict[str, Any] = {"json": {}} if method in {"POST", "PATCH", "PUT"} else {}
            response = a.request(method, path, **options)
            if response.status_code != 404:
                failures.append(f"{method} {route.path} -> {response.status_code}")

    assert failures == []


def test_every_org_scoped_route_returns_401_without_a_session(app: FastAPI, api: Api) -> None:
    anon = api.anonymous()
    org = str(uuid.uuid4())
    failures: list[str] = []
    routes = [r for r in iter_api_routes(app) if "/{org_id}" in r.path]
    assert len(routes) >= 10, "route discovery found suspiciously few org-scoped routes"
    for route in routes:
        path = fill_path(route, org_id=org)
        for method in route.sendable_methods:
            options: dict[str, Any] = {"json": {}} if method in {"POST", "PATCH", "PUT"} else {}
            response = anon.request(method, path, cookie=None, **options)
            if response.status_code != 401:
                failures.append(f"{method} {route.path} -> {response.status_code}")

    assert failures == []


def test_organization_switching_does_not_leak_data(api: Api) -> None:
    """One session, two orgs, interleaved requests: each response only ever shows its own org."""
    user = api.signup(org_name="Home Org")
    other_owner = api.signup(org_name="Work Org")
    _invite_into(api, other_owner, user, "agent")
    home, work = user.org_id, other_owner.org_id
    home_emails, work_emails = {user.email}, {other_owner.email, user.email}

    for _ in range(8):
        for org_id, expected in ((home, home_emails), (work, work_emails)):
            members = user.get(f"/orgs/{org_id}/members").json()["data"]
            assert {m["user"]["email"] for m in members} == expected
            assert user.get(f"/orgs/{org_id}").json()["id"] == org_id
            logged = user.get(f"/orgs/{org_id}/audit-logs") if org_id == home else None
            if logged is not None:
                assert all(e["target_id"] != work for e in logged.json()["data"])

    # Roles differ per org and are applied per request, never carried over.
    assert user.get(f"/orgs/{home}").json()["role"] == "owner"
    assert user.get(f"/orgs/{work}").json()["role"] == "agent"
    assert user.patch(f"/orgs/{work}", {"name": "nope"}).status_code == 403
    assert user.patch(f"/orgs/{home}", {"name": "Home renamed"}).status_code == 200
    assert other_owner.get(f"/orgs/{work}").json()["name"] == "Work Org"


def test_switching_orgs_after_leaving_one_does_not_keep_stale_access(api: Api) -> None:
    user = api.signup()
    other_owner = api.signup()
    _invite_into(api, other_owner, user, "viewer")
    work = other_owner.org_id
    assert user.get(f"/orgs/{work}/members").status_code == 200
    my_membership = next(
        m["id"]
        for m in other_owner.get(f"/orgs/{work}/members").json()["data"]
        if m["user"]["id"] == user.user_id
    )

    other_owner.delete(f"/orgs/{work}/members/{my_membership}")

    assert user.get(f"/orgs/{work}/members").status_code == 404
    assert user.get(f"/orgs/{user.org_id}/members").status_code == 200


def test_database_context_is_transaction_scoped_and_never_leaks_between_requests(
    app: FastAPI, api: Api
) -> None:
    """After many requests across orgs, a connection from the API's own pool carries no context."""
    a, b = _two_tenants(api)
    for _ in range(5):
        a.get(f"/orgs/{a.org_id}/members")
        b.get(f"/orgs/{b.org_id}/members")

    import asyncio

    from sqlalchemy import text

    async def probe() -> tuple[str | None, str | None]:
        engine = app.state.engine
        async with engine.connect() as conn:
            org = await conn.scalar(text("SELECT current_setting('app.current_org_id', true)"))
            user = await conn.scalar(text("SELECT current_setting('app.current_user_id', true)"))
            return org, user

    # The app's engine is bound to the TestClient's loop; run the probe in that loop.
    org, user = api.client.portal.call(probe)  # type: ignore[union-attr]
    assert org in (None, "")
    assert user in (None, "")
    del asyncio


def test_runtime_credentials_cannot_bypass_row_level_security(app: FastAPI, api: Api) -> None:
    """The API's own connection is the unprivileged role: no superuser, no BYPASSRLS."""
    from sqlalchemy import text

    async def probe() -> tuple[bool, bool]:
        async with app.state.engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
                )
            ).one()
            return row.rolsuper, row.rolbypassrls

    assert api.client.portal.call(probe) == (False, False)  # type: ignore[union-attr]
