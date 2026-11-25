"""ORM → response model mapping (explicit, so no column can leak by accident)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.schemas.auth import OrgRoleOut, UserOut
from app.schemas.orgs import MemberOut, MemberUser, OrgOut
from app.services.tenancy.policy import PERMISSIONS, Role

if TYPE_CHECKING:
    from app.models.identity import User
    from app.models.tenancy import Membership, Organization


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        email_verified=user.email_verified_at is not None,
        locale=user.locale,
    )


def org_role_out(org: Organization, role: str) -> OrgRoleOut:
    return OrgRoleOut(id=org.id, name=org.name, role=role)


def org_out(org: Organization, role: str) -> OrgOut:
    return OrgOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        status=org.status,
        role=role,
        permissions=sorted(PERMISSIONS[Role(role)]),
        settings=org.settings,
        created_at=org.created_at,
    )


def member_out(member: Membership, user: User) -> MemberOut:
    return MemberOut(
        id=member.id,
        user=MemberUser(
            id=user.id,
            name=user.name,
            email=user.email,
            email_verified=user.email_verified_at is not None,
        ),
        role=member.role,
        created_at=member.created_at,
    )
