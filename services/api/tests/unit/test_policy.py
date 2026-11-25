"""RBAC and membership policy rules — pure functions, no I/O (docs/SECURITY.md §4)."""

from __future__ import annotations

import pytest

from app.services.tenancy.policy import (
    PERMISSIONS,
    PolicyError,
    Role,
    can_invite_role,
    check_leave,
    check_member_removal,
    check_role_change,
    has_permission,
)


def test_role_names_match_database_check_constraint() -> None:
    assert {role.value for role in Role} == {"owner", "admin", "agent", "viewer"}


def test_every_role_can_read_org_but_only_owner_can_delete_or_transfer() -> None:
    for role in Role:
        assert has_permission(role, "org:read")
    assert has_permission(Role.OWNER, "org:transfer")
    for role in (Role.ADMIN, Role.AGENT, Role.VIEWER):
        assert not has_permission(role, "org:transfer")
        assert not has_permission(role, "org:delete")


def test_agent_cannot_manage_members_or_billing_or_org_settings() -> None:
    for permission in (
        "member:invite",
        "member:manage",
        "org:update",
        "audit:read",
        "billing:manage",
    ):
        assert not has_permission(Role.AGENT, permission)


def test_viewer_is_read_only() -> None:
    writes = {p for p in PERMISSIONS[Role.VIEWER] if p.endswith((":write", ":manage", ":delete"))}
    assert writes == set()


def test_roles_are_strictly_nested() -> None:
    assert PERMISSIONS[Role.VIEWER] < PERMISSIONS[Role.AGENT] < PERMISSIONS[Role.ADMIN]
    assert PERMISSIONS[Role.ADMIN] < PERMISSIONS[Role.OWNER]


def test_unknown_permission_is_denied() -> None:
    assert not has_permission(Role.OWNER, "nonexistent:permission")


@pytest.mark.parametrize(
    ("actor", "invited", "allowed"),
    [
        (Role.OWNER, Role.ADMIN, True),
        (Role.OWNER, Role.OWNER, False),  # owner only via transfer
        (Role.ADMIN, Role.AGENT, True),
        (Role.ADMIN, Role.ADMIN, True),
        (Role.ADMIN, Role.OWNER, False),
        (Role.AGENT, Role.VIEWER, False),
        (Role.VIEWER, Role.VIEWER, False),
    ],
)
def test_can_invite_role(actor: Role, invited: Role, allowed: bool) -> None:
    assert can_invite_role(actor, invited) is allowed


def test_admin_can_demote_agent_to_viewer() -> None:
    check_role_change(
        actor_role=Role.ADMIN,
        actor_is_target=False,
        target_role=Role.AGENT,
        new_role=Role.VIEWER,
    )


def test_agent_cannot_change_any_role() -> None:
    with pytest.raises(PolicyError) as exc:
        check_role_change(
            actor_role=Role.AGENT,
            actor_is_target=False,
            target_role=Role.VIEWER,
            new_role=Role.AGENT,
        )
    assert exc.value.code == "forbidden"


def test_member_cannot_change_own_role() -> None:
    with pytest.raises(PolicyError) as exc:
        check_role_change(
            actor_role=Role.ADMIN,
            actor_is_target=True,
            target_role=Role.ADMIN,
            new_role=Role.OWNER,
        )
    assert exc.value.code == "forbidden"


def test_admin_cannot_modify_an_owner() -> None:
    with pytest.raises(PolicyError) as exc:
        check_role_change(
            actor_role=Role.ADMIN,
            actor_is_target=False,
            target_role=Role.OWNER,
            new_role=Role.VIEWER,
        )
    assert exc.value.code == "forbidden"


@pytest.mark.parametrize("actor", [Role.OWNER, Role.ADMIN])
def test_nobody_can_promote_to_owner_via_role_change(actor: Role) -> None:
    with pytest.raises(PolicyError) as exc:
        check_role_change(
            actor_role=actor,
            actor_is_target=False,
            target_role=Role.ADMIN,
            new_role=Role.OWNER,
        )
    assert exc.value.code == "forbidden"


def test_owner_can_demote_another_owner() -> None:
    check_role_change(
        actor_role=Role.OWNER,
        actor_is_target=False,
        target_role=Role.OWNER,
        new_role=Role.ADMIN,
    )


def test_admin_cannot_remove_owner_but_can_remove_agent() -> None:
    with pytest.raises(PolicyError):
        check_member_removal(actor_role=Role.ADMIN, target_role=Role.OWNER)
    check_member_removal(actor_role=Role.ADMIN, target_role=Role.AGENT)


def test_agent_cannot_remove_members() -> None:
    with pytest.raises(PolicyError):
        check_member_removal(actor_role=Role.AGENT, target_role=Role.VIEWER)


def test_last_owner_cannot_leave() -> None:
    with pytest.raises(PolicyError) as exc:
        check_leave(role=Role.OWNER, owner_count=1)
    assert exc.value.code == "last_owner"


def test_owner_can_leave_when_another_owner_exists_and_non_owners_can_always_leave() -> None:
    check_leave(role=Role.OWNER, owner_count=2)
    check_leave(role=Role.VIEWER, owner_count=1)
