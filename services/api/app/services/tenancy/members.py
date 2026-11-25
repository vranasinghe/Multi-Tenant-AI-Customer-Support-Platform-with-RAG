"""Membership management. Every rule lives in ``policy`` (pure, tested); this module only loads
rows under lock, applies the verdict, writes the change and records the audit entry."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.errors import ApiError, forbidden, not_found
from app.models.identity import User
from app.models.tenancy import Membership
from app.services.tenancy.audit import record_audit
from app.services.tenancy.policy import (
    PolicyError,
    Role,
    check_leave,
    check_member_removal,
    check_role_change,
    has_permission,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.request_meta import RequestMeta
    from app.services.tenancy.context import TenantContext


def policy_to_api(exc: PolicyError) -> ApiError:
    if exc.code == "last_owner":
        return ApiError(409, "last_owner", "Last owner", detail=exc.detail)
    return forbidden(exc.detail)


async def list_members(db: AsyncSession, ctx: TenantContext) -> list[tuple[Membership, User]]:
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == ctx.org.id)
        .order_by(Membership.created_at, Membership.id)
    )
    return [(row[0], row[1]) for row in (await db.execute(stmt)).all()]


async def _load_member(
    db: AsyncSession, ctx: TenantContext, membership_id: uuid.UUID
) -> Membership:
    # The org filter is redundant with RLS on purpose (defence in depth). FOR UPDATE serialises
    # concurrent role changes/removals so the last-owner rule cannot be raced.
    member = await db.scalar(
        select(Membership)
        .where(Membership.id == membership_id, Membership.org_id == ctx.org.id)
        .with_for_update()
    )
    if member is None:
        raise not_found()
    return member


async def _owner_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    owners = await db.scalars(
        select(Membership.id)
        .where(Membership.org_id == org_id, Membership.role == Role.OWNER.value)
        .with_for_update()
    )
    return len(owners.all())


async def change_role(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    membership_id: uuid.UUID,
    new_role: Role,
    meta: RequestMeta,
) -> Membership:
    member = await _load_member(db, ctx, membership_id)
    old_role = Role(member.role)
    try:
        check_role_change(
            actor_role=ctx.role,
            actor_is_target=member.user_id == ctx.user.id,
            target_role=old_role,
            new_role=new_role,
        )
    except PolicyError as exc:
        raise policy_to_api(exc) from exc
    if old_role is new_role:
        return member
    member.role = new_role.value
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="member.role_changed",
        target_type="membership",
        target_id=member.id,
        metadata={"user_id": str(member.user_id), "from": old_role.value, "to": new_role.value},
        meta=meta,
    )
    return member


async def remove_member(
    db: AsyncSession, ctx: TenantContext, *, membership_id: uuid.UUID, meta: RequestMeta
) -> None:
    """Remove someone else (needs ``member:manage``) or leave the org (any member)."""
    member = await _load_member(db, ctx, membership_id)
    role = Role(member.role)
    leaving = member.user_id == ctx.user.id
    try:
        if leaving:
            check_leave(role=role, owner_count=await _owner_count(db, ctx.org.id))
        else:
            check_member_removal(actor_role=ctx.role, target_role=role)
    except PolicyError as exc:
        raise policy_to_api(exc) from exc
    target_user_id = member.user_id
    await db.delete(member)
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="member.left" if leaving else "member.removed",
        target_type="membership",
        target_id=membership_id,
        metadata={"user_id": str(target_user_id), "role": role.value},
        meta=meta,
    )


async def transfer_ownership(
    db: AsyncSession,
    ctx: TenantContext,
    *,
    new_owner_user_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    """Owner → admin becomes owner; the previous owner becomes admin (the only way to mint an
    owner). Order matters: promote first so the last-owner trigger is never violated."""
    if not has_permission(ctx.role, "org:transfer"):
        raise forbidden("Only an owner can transfer ownership.")
    if new_owner_user_id == ctx.user.id:
        raise forbidden("You already own this organization.")
    target = await db.scalar(
        select(Membership)
        .where(Membership.org_id == ctx.org.id, Membership.user_id == new_owner_user_id)
        .with_for_update()
    )
    if target is None:
        raise not_found()
    if target.role != Role.ADMIN.value:
        raise ApiError(
            409, "conflict", "Not an admin", detail="Ownership can only pass to an admin."
        )
    me = await db.scalar(
        select(Membership)
        .where(Membership.id == ctx.membership_id, Membership.org_id == ctx.org.id)
        .with_for_update()
    )
    if me is None:
        raise not_found()
    target.role = Role.OWNER.value
    await db.flush()
    me.role = Role.ADMIN.value
    await db.flush()
    await record_audit(
        db,
        org_id=ctx.org.id,
        actor_id=ctx.user.id,
        action="org.ownership_transferred",
        target_type="organization",
        target_id=ctx.org.id,
        metadata={"from_user_id": str(ctx.user.id), "to_user_id": str(new_owner_user_id)},
        meta=meta,
    )
