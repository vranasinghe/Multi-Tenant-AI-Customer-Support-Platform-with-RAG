"""Detached authorization facts, revalidated after slow preparation before any generation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ApiError, forbidden, not_found, unauthenticated
from app.models.identity import User, UserSession, utcnow
from app.models.tenancy import Membership, Organization
from app.services.tenancy.context import set_org_context, set_user_context
from app.services.tenancy.policy import Role, has_permission


@dataclass(frozen=True)
class ChatAccess:
    org_id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID
    permission: str
    verified: bool

    async def validate(self, db: AsyncSession, settings: Settings) -> None:
        now = utcnow()
        user = await db.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                User.id == self.user_id,
                UserSession.id == self.session_id,
                User.status == "active",
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                UserSession.last_seen_at > now - timedelta(days=settings.session_idle_days),
            )
        )
        if user is None:
            raise unauthenticated()
        await set_user_context(db, user.id)
        membership = await db.scalar(
            select(Membership).where(
                Membership.org_id == self.org_id,
                Membership.user_id == user.id,
            )
        )
        if membership is None:
            raise not_found()
        await set_org_context(db, membership.org_id)
        org = await db.get(Organization, membership.org_id)
        if org is None or org.deleted_at is not None:
            raise not_found()
        if not has_permission(Role(membership.role), self.permission):
            raise forbidden()
        if self.verified and user.email_verified_at is None:
            raise forbidden("Verify your email address to continue.", code="email_not_verified")
        if org.status != "active":
            raise ApiError(403, "org_restricted", "Organization is read-only")
