"""Opaque server-side sessions (ADR-004): 256-bit token in a cookie, SHA-256 hash in Postgres.

There is deliberately no cache in front of this lookup in this phase: every request is checked
against the database, so logout, password reset, membership removal and account disabling take
effect on the very next request.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update

from app.core.security import hash_token, new_token
from app.models.identity import User, UserSession, utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.config import Settings
    from app.core.request_meta import RequestMeta


async def create_session(
    db: AsyncSession, *, user_id: uuid.UUID, settings: Settings, meta: RequestMeta
) -> str:
    """Insert a session row and return the raw token (shown to the client exactly once)."""
    token = new_token()
    now = utcnow()
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=settings.session_absolute_days),
            user_agent=meta.user_agent,
            ip_prefix=meta.ip_prefix,
        )
    )
    await db.flush()
    return token


async def find_active_session(
    db: AsyncSession, *, token: str, settings: Settings
) -> tuple[User, UserSession] | None:
    """The user+session for a cookie token, or None if unknown/revoked/expired/idle/disabled."""
    stmt = (
        select(User, UserSession)
        .join(User, User.id == UserSession.user_id)
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
            UserSession.last_seen_at > func.now() - timedelta(days=settings.session_idle_days),
            User.status == "active",
        )
    )
    row = (await db.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def touch_session(
    factory: async_sessionmaker[AsyncSession], *, session_id: uuid.UUID, settings: Settings
) -> None:
    """Slide the idle window at most once per interval, in its own short transaction."""
    stale_before = func.now() - timedelta(seconds=settings.session_touch_interval_seconds)
    async with factory() as db, db.begin():
        await db.execute(
            update(UserSession)
            .where(UserSession.id == session_id, UserSession.last_seen_at < stale_before)
            .values(last_seen_at=func.now())
        )


async def revoke_session_by_token(db: AsyncSession, token: str) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.token_hash == hash_token(token), UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


async def revoke_user_sessions(
    db: AsyncSession, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None
) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    result = await db.execute(stmt)
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def revoke_one(db: AsyncSession, *, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
    result = await db.execute(
        update(UserSession)
        .where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=func.now())
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[UserSession]:
    stmt = (
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
        )
        .order_by(UserSession.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())
