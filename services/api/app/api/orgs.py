"""Organization-scoped endpoints. The org id in the path is verified against the caller's own
membership by ``require(...)`` on every request; bodies never carry an org id."""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    AuthDep,
    DbDep,
    MailDep,
    MetaDep,
    ServicesDep,
    VerifiedAuthDep,
    require,
)
from app.api.serializers import member_out, org_out
from app.core.errors import ApiError, not_found
from app.core.rate_limit import Limit
from app.models.identity import User
from app.models.tenancy import Invitation
from app.schemas.orgs import (
    AuditActor,
    AuditLogList,
    AuditLogOut,
    CreateOrgRequest,
    InvitationList,
    InvitationOut,
    InviteRequest,
    MemberList,
    MemberOut,
    OrgList,
    OrgOut,
    TransferOwnershipRequest,
    UpdateMemberRequest,
    UpdateOrgRequest,
)
from app.services.tenancy import audit, invitations, members, orgs
from app.services.tenancy.context import TenantContext
from app.services.tenancy.policy import Role

router = APIRouter(prefix="/orgs", tags=["organizations"])

# Declared permission per route (asserted by tests/integration/api/test_route_permissions.py).
OrgRead = Annotated[TenantContext, Depends(require("org:read"))]
OrgUpdate = Annotated[TenantContext, Depends(require("org:update"))]
OrgTransfer = Annotated[TenantContext, Depends(require("org:transfer", verified=True))]
MemberRead = Annotated[TenantContext, Depends(require("member:read"))]
MemberManage = Annotated[TenantContext, Depends(require("member:manage"))]
MemberInvite = Annotated[TenantContext, Depends(require("member:invite", verified=True))]
InviteView = Annotated[TenantContext, Depends(require("member:invite"))]
AuditRead = Annotated[TenantContext, Depends(require("audit:read"))]


@router.get("")
async def list_orgs(auth: AuthDep, db: DbDep) -> OrgList:
    rows = await orgs.list_user_orgs(db, auth.user.id)
    return OrgList(data=[org_out(org, role) for org, role in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_org(
    body: CreateOrgRequest, auth: VerifiedAuthDep, db: DbDep, meta: MetaDep
) -> OrgOut:
    org, membership = await orgs.create_organization(
        db, creator=auth.user, name=body.name, meta=meta
    )
    await db.commit()
    return org_out(org, membership.role)


@router.get("/{org_id}")
async def get_org(org_id: uuid.UUID, ctx: OrgRead) -> OrgOut:
    return org_out(ctx.org, ctx.role.value)


@router.patch("/{org_id}")
async def update_org(
    org_id: uuid.UUID, body: UpdateOrgRequest, ctx: OrgUpdate, db: DbDep, meta: MetaDep
) -> OrgOut:
    await orgs.update_organization(
        db,
        org=ctx.org,
        actor_id=ctx.user.id,
        name=body.name,
        settings=body.settings.model_dump(exclude_none=True) if body.settings else None,
        meta=meta,
    )
    await db.commit()
    return org_out(ctx.org, ctx.role.value)


@router.post("/{org_id}/transfer-ownership")
async def transfer_ownership(
    org_id: uuid.UUID,
    body: TransferOwnershipRequest,
    ctx: OrgTransfer,
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
) -> OrgOut:
    """Re-authentication required: the owner must re-enter their password."""
    await svc.limiter.check(str(ctx.user.id), Limit("reauth", 5, 60))
    if not await svc.passwords.verify(ctx.user.password_hash, body.password):
        raise ApiError(400, "invalid_credentials", "Password is incorrect")
    await members.transfer_ownership(db, ctx, new_owner_user_id=body.new_owner_user_id, meta=meta)
    await db.commit()
    return org_out(ctx.org, Role.ADMIN.value)


# ------------------------------------------------------------------------------ members


@router.get("/{org_id}/members")
async def list_members(org_id: uuid.UUID, ctx: MemberRead, db: DbDep) -> MemberList:
    rows = await members.list_members(db, ctx)
    return MemberList(data=[member_out(member, user) for member, user in rows])


@router.patch("/{org_id}/members/{membership_id}")
async def change_member_role(
    org_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: UpdateMemberRequest,
    ctx: MemberManage,
    db: DbDep,
    meta: MetaDep,
) -> MemberOut:
    member = await members.change_role(
        db, ctx, membership_id=membership_id, new_role=Role(body.role), meta=meta
    )
    await db.commit()
    user = await db.get(User, member.user_id)
    if user is None:  # pragma: no cover - FK guarantees the row exists
        raise not_found()
    return member_out(member, user)


@router.delete("/{org_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: uuid.UUID, membership_id: uuid.UUID, ctx: OrgRead, db: DbDep, meta: MetaDep
) -> None:
    """Remove a member (needs ``member:manage``) or leave the organization (any member removing
    their own membership). The distinction is enforced by the membership policy."""
    await members.remove_member(db, ctx, membership_id=membership_id, meta=meta)
    await db.commit()


# -------------------------------------------------------------------------- invitations


def _invitation_out(invitation: Invitation) -> InvitationOut:
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        status=invitations.invitation_status(invitation),
        expires_at=invitation.expires_at,
        created_at=invitation.created_at,
    )


@router.get("/{org_id}/invitations")
async def list_invitations(org_id: uuid.UUID, ctx: InviteView, db: DbDep) -> InvitationList:
    rows = await invitations.list_invitations(db, ctx)
    return InvitationList(data=[_invitation_out(row) for row in rows])


@router.post("/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    org_id: uuid.UUID,
    body: InviteRequest,
    ctx: MemberInvite,
    db: DbDep,
    svc: ServicesDep,
    mail: MailDep,
    meta: MetaDep,
) -> InvitationOut:
    invitation = await invitations.create_invitation(
        db, svc, mail, ctx, email=str(body.email), role=Role(body.role), meta=meta
    )
    return _invitation_out(invitation)


@router.post("/{org_id}/invitations/{invitation_id}/resend", status_code=status.HTTP_200_OK)
async def resend_invitation(
    org_id: uuid.UUID,
    invitation_id: uuid.UUID,
    ctx: MemberInvite,
    db: DbDep,
    svc: ServicesDep,
    mail: MailDep,
    meta: MetaDep,
) -> InvitationOut:
    invitation = await invitations.resend_invitation(
        db, svc, mail, ctx, invitation_id=invitation_id, meta=meta
    )
    return _invitation_out(invitation)


@router.delete("/{org_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(
    org_id: uuid.UUID, invitation_id: uuid.UUID, ctx: InviteView, db: DbDep, meta: MetaDep
) -> None:
    await invitations.revoke_invitation(db, ctx, invitation_id=invitation_id, meta=meta)
    await db.commit()


# ------------------------------------------------------------------------------- audit


def _encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        stamp, row_id = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(stamp), uuid.UUID(row_id)
    except (ValueError, binascii.Error) as exc:
        raise ApiError(400, "invalid_cursor", "Invalid cursor") from exc


@router.get("/{org_id}/audit-logs")
async def list_audit_logs(
    org_id: uuid.UUID,
    ctx: AuditRead,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
) -> AuditLogList:
    rows = await audit.list_audit_logs(
        db,
        org_id=ctx.org.id,
        limit=limit,
        before=_decode_cursor(cursor) if cursor else None,
        action=action,
    )
    page = rows[:limit]
    has_more = len(rows) > limit
    data = [
        AuditLogOut(
            id=entry.id,
            action=entry.action,
            actor=AuditActor(id=actor.id, name=actor.name) if actor else None,
            actor_type=entry.actor_type,
            target_type=entry.target_type,
            target_id=entry.target_id,
            metadata=entry.meta,
            request_id=entry.request_id,
            created_at=entry.created_at,
        )
        for entry, actor in page
    ]
    last = page[-1][0] if page else None
    return AuditLogList(
        data=data,
        next_cursor=_encode_cursor(last.created_at, last.id) if has_more and last else None,
        has_more=has_more,
    )
