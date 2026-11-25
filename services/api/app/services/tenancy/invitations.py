"""Team invitations: expiring, single-use, email-bound tokens (docs/ARCHITECTURE.md §7.2)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text, update

from app.core.errors import ApiError, forbidden, invalid_token, not_found
from app.core.security import hash_token, new_token
from app.models.identity import User, utcnow
from app.models.tenancy import Invitation, Membership, Organization
from app.services import notifications
from app.services.tenancy.audit import record_audit
from app.services.tenancy.context import set_org_context, set_user_context
from app.services.tenancy.policy import Role, can_invite_role

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.services.container import AppServices, MailQueue
    from app.services.tenancy.context import TenantContext


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if local else f"***@{domain}"


def invitation_status(invitation: Invitation) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= utcnow():
        return "expired"
    return "pending"


def _send_invite_mail(
    svc: AppServices,
    mail: MailQueue,
    *,
    org: Organization,
    inviter: User,
    email: str,
    role: str,
    token: str,
) -> None:
    mail.send(
        notifications.invitation(
            to=email,
            org_name=org.name,
            inviter_name=inviter.name,
            role=role,
            web_base_url=svc.settings.web_base_url,
            token=token,
        )
    )


async def create_invitation(
    db: AsyncSession,
    svc: AppServices,
    mail: MailQueue,
    ctx: TenantContext,
    *,
    email: str,
    role: Role,
    meta: RequestMeta,
) -> Invitation:
    if not can_invite_role(ctx.role, role):
        raise forbidden("You cannot invite someone with that role.")

    already_member = await db.scalar(
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == ctx.org.id, User.email == email)
    )
    if already_member is not None:
        raise ApiError(409, "already_member", "Already a member")

    pending = await db.scalar(
        select(Invitation)
        .where(
            Invitation.org_id == ctx.org.id,
            Invitation.email == email,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if pending is not None:
        if pending.expires_at > utcnow():
            raise ApiError(
                409, "conflict", "Invitation already pending", detail="Resend it instead."
            )
        pending.revoked_at = utcnow()  # free the slot held by an expired invitation
        await db.flush()

    token = new_token()
    invitation = Invitation(
        org_id=ctx.org.id,
        email=email,
        role=role.value,
        token_hash=hash_token(token),
        invited_by=ctx.user.id,
        expires_at=utcnow() + timedelta(days=svc.settings.invitation_ttl_days),
    )
    db.add(invitation)
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="member.invited",
        target_type="invitation",
        target_id=invitation.id,
        metadata={"email": email, "role": role.value},
        meta=meta,
    )
    await db.commit()
    _send_invite_mail(
        svc, mail, org=ctx.org, inviter=ctx.user, email=email, role=role.value, token=token
    )
    return invitation


async def list_invitations(db: AsyncSession, ctx: TenantContext) -> list[Invitation]:
    stmt = (
        select(Invitation)
        .where(
            Invitation.org_id == ctx.org.id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .order_by(Invitation.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())


async def _load_invitation(
    db: AsyncSession, ctx: TenantContext, invitation_id: uuid.UUID
) -> Invitation:
    invitation = await db.scalar(
        select(Invitation)
        .where(Invitation.id == invitation_id, Invitation.org_id == ctx.org.id)
        .with_for_update()
    )
    if invitation is None or invitation.accepted_at is not None or invitation.revoked_at:
        raise not_found()
    return invitation


async def resend_invitation(
    db: AsyncSession,
    svc: AppServices,
    mail: MailQueue,
    ctx: TenantContext,
    *,
    invitation_id: uuid.UUID,
    meta: RequestMeta,
) -> Invitation:
    """Issues a fresh token and expiry; the previously emailed link stops working."""
    invitation = await _load_invitation(db, ctx, invitation_id)
    token = new_token()
    invitation.token_hash = hash_token(token)
    invitation.expires_at = utcnow() + timedelta(days=svc.settings.invitation_ttl_days)
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="invitation.resent",
        target_type="invitation",
        target_id=invitation.id,
        metadata={"email": invitation.email},
        meta=meta,
    )
    await db.commit()
    _send_invite_mail(
        svc,
        mail,
        org=ctx.org,
        inviter=ctx.user,
        email=invitation.email,
        role=invitation.role,
        token=token,
    )
    return invitation


async def revoke_invitation(
    db: AsyncSession, ctx: TenantContext, *, invitation_id: uuid.UUID, meta: RequestMeta
) -> None:
    invitation = await _load_invitation(db, ctx, invitation_id)
    invitation.revoked_at = utcnow()
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="invitation.revoked",
        target_type="invitation",
        target_id=invitation.id,
        metadata={"email": invitation.email},
        meta=meta,
    )


# ----------------------------------------------------- token-based (pre-tenant) paths


@dataclass(frozen=True)
class ResolvedInvitation:
    invitation_id: uuid.UUID
    org_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None

    @property
    def usable(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None and self.expires_at > utcnow()


async def resolve_invitation(db: AsyncSession, token: str) -> ResolvedInvitation:
    """Look a token up through the narrow SECURITY DEFINER resolver (no tenant context yet).

    Unknown, expired, used and revoked tokens are indistinguishable to the caller.
    """
    row = (
        await db.execute(
            text(
                "SELECT invitation_id, org_id, email, role, expires_at, accepted_at, revoked_at "
                "FROM app.resolve_invitation(:h)"
            ),
            {"h": hash_token(token)},
        )
    ).first()
    if row is None:
        raise invalid_token()
    resolved = ResolvedInvitation(*row)
    if not resolved.usable:
        raise invalid_token()
    return resolved


@dataclass(frozen=True)
class InvitationPreview:
    org_name: str
    inviter_name: str | None
    role: str
    email_hint: str


async def lookup_invitation(db: AsyncSession, token: str) -> InvitationPreview:
    resolved = await resolve_invitation(db, token)
    await set_org_context(db, resolved.org_id)
    org = await db.get(Organization, resolved.org_id)
    invitation = await db.get(Invitation, resolved.invitation_id)
    if org is None or invitation is None:
        raise invalid_token()
    inviter = await db.get(User, invitation.invited_by) if invitation.invited_by else None
    return InvitationPreview(
        org_name=org.name,
        inviter_name=inviter.name if inviter else None,
        role=resolved.role,
        email_hint=mask_email(resolved.email),
    )


async def accept_invitation(
    db: AsyncSession, *, user: User, token: str, meta: RequestMeta
) -> tuple[Organization, Membership]:
    resolved = await resolve_invitation(db, token)
    # Email binding: a forwarded link cannot be accepted by a different account.
    if resolved.email.lower() != user.email.lower():
        raise forbidden("This invitation was sent to a different email address.")

    await set_user_context(db, user.id)
    await set_org_context(db, resolved.org_id)
    existing = await db.scalar(
        select(Membership.id).where(
            Membership.org_id == resolved.org_id, Membership.user_id == user.id
        )
    )
    if existing is not None:
        raise ApiError(409, "already_member", "Already a member")

    # Atomic single-use: only one concurrent accept can flip accepted_at.
    spent = await db.execute(
        update(Invitation)
        .where(
            Invitation.id == resolved.invitation_id,
            Invitation.org_id == resolved.org_id,
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > func.now(),
        )
        .values(accepted_at=func.now())
        .returning(Invitation.id)
    )
    if spent.scalar_one_or_none() is None:
        raise invalid_token()

    membership = Membership(org_id=resolved.org_id, user_id=user.id, role=resolved.role)
    db.add(membership)
    await db.flush()
    org = await db.get(Organization, resolved.org_id)
    if org is None:
        raise invalid_token()
    await record_audit(
        db,
        org_id=resolved.org_id,
        actor_id=user.id,
        action="invitation.accepted",
        target_type="invitation",
        target_id=resolved.invitation_id,
        metadata={"role": resolved.role},
        meta=meta,
    )
    return org, membership
