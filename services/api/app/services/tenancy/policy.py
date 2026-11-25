"""RBAC permission matrix and membership policy rules.

Pure functions, no I/O, so they are exhaustively unit-testable (docs/SECURITY.md §4, ADR-005).
Role names: owner > admin > agent > viewer (``agent`` is the content-editing tier).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class PolicyError(Exception):
    """A membership/RBAC rule was violated. ``code`` maps to the API error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


_VIEWER: frozenset[str] = frozenset(
    {
        "org:read",
        "member:read",
        "usage:read",
        "analytics:read",
        "chatbot:read",
        "knowledge:read",
        "channel:read",
        "conversation:read",
    }
)
_AGENT: frozenset[str] = _VIEWER | {
    "chatbot:write",
    "knowledge:write",
    "chatbot:test",
    "conversation:debug",
}
_ADMIN: frozenset[str] = _AGENT | {
    "org:update",
    "member:invite",
    "member:manage",
    "audit:read",
    "billing:read",
    "chatbot:delete",
    "domain:manage",
    "channel:manage",
    "conversation:delete",
    "conversation:export",
}
_OWNER: frozenset[str] = _ADMIN | {"org:delete", "org:transfer", "billing:manage"}

PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.VIEWER: _VIEWER,
    Role.AGENT: _AGENT,
    Role.ADMIN: _ADMIN,
    Role.OWNER: _OWNER,
}

ALL_PERMISSIONS: frozenset[str] = _OWNER


def has_permission(role: Role, permission: str) -> bool:
    return permission in PERMISSIONS[role]


def can_invite_role(actor_role: Role, invited_role: Role) -> bool:
    """Owners are never invited: ownership moves only through transfer."""
    if invited_role is Role.OWNER:
        return False
    return has_permission(actor_role, "member:invite")


def check_role_change(
    *, actor_role: Role, actor_is_target: bool, target_role: Role, new_role: Role
) -> None:
    if not has_permission(actor_role, "member:manage"):
        raise PolicyError("forbidden", "Your role cannot manage members.")
    if actor_is_target:
        raise PolicyError("forbidden", "You cannot change your own role.")
    if new_role is Role.OWNER:
        raise PolicyError("forbidden", "Ownership can only be transferred, not granted.")
    if target_role is Role.OWNER and actor_role is not Role.OWNER:
        raise PolicyError("forbidden", "Only an owner can change an owner.")


def check_member_removal(*, actor_role: Role, target_role: Role) -> None:
    if not has_permission(actor_role, "member:manage"):
        raise PolicyError("forbidden", "Your role cannot remove members.")
    if target_role is Role.OWNER and actor_role is not Role.OWNER:
        raise PolicyError("forbidden", "Only an owner can remove an owner.")


def check_leave(*, role: Role, owner_count: int) -> None:
    if role is Role.OWNER and owner_count <= 1:
        raise PolicyError("last_owner", "An organization must keep at least one owner.")
