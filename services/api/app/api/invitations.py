"""Token-based invitation endpoints (no org id in the URL; the token resolves the tenant)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep, MetaDep, ServicesDep, VerifiedAuthDep
from app.api.serializers import org_role_out
from app.core.rate_limit import Limit
from app.schemas.auth import OrgRoleOut
from app.schemas.orgs import AcceptInvitationRequest, InvitationPreviewOut
from app.services.tenancy import invitations

router = APIRouter(prefix="/invitations", tags=["invitations"])


@router.get("/lookup")
async def lookup_invitation(
    db: DbDep,
    svc: ServicesDep,
    meta: MetaDep,
    token: str = Query(min_length=20, max_length=128),
) -> InvitationPreviewOut:
    """Public: what the invite page shows before sign-in (org, inviter, masked email)."""
    await svc.limiter.check(
        meta.ip or "unknown",
        Limit("invite_lookup", svc.settings.rate_limit_invite_lookup_per_minute, 60),
    )
    preview = await invitations.lookup_invitation(db, token)
    return InvitationPreviewOut(
        org_name=preview.org_name,
        inviter_name=preview.inviter_name,
        role=preview.role,
        email_hint=preview.email_hint,
    )


@router.post("/accept")
async def accept_invitation(
    body: AcceptInvitationRequest, auth: VerifiedAuthDep, db: DbDep, meta: MetaDep
) -> OrgRoleOut:
    org, membership = await invitations.accept_invitation(
        db, user=auth.user, token=body.token, meta=meta
    )
    await db.commit()
    return org_role_out(org, membership.role)
