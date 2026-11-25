"""Single-use emailed tokens (verify email, reset password). Only SHA-256 hashes are stored."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import func, update

from app.core.security import hash_token, new_token
from app.models.identity import EmailToken, utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

Purpose = Literal["verify_email", "reset_password", "change_email"]


async def issue_email_token(
    db: AsyncSession, *, user_id: uuid.UUID, purpose: Purpose, ttl: timedelta
) -> str:
    """Create a token; any earlier unconsumed token of the same purpose is invalidated."""
    await db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.consumed_at.is_(None),
        )
        .values(consumed_at=func.now())
    )
    token = new_token()
    now = utcnow()
    db.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=now + ttl,
            created_at=now,
        )
    )
    await db.flush()
    return token


async def consume_email_token(
    db: AsyncSession, *, token: str, purpose: Purpose
) -> uuid.UUID | None:
    """Atomically spend a token and return its user id, or None if unknown/used/expired/wrong
    purpose. One UPDATE ... RETURNING makes concurrent double-spends impossible."""
    result = await db.execute(
        update(EmailToken)
        .where(
            EmailToken.token_hash == hash_token(token),
            EmailToken.purpose == purpose,
            EmailToken.consumed_at.is_(None),
            EmailToken.expires_at > func.now(),
        )
        .values(consumed_at=func.now())
        .returning(EmailToken.user_id)
    )
    return result.scalar_one_or_none()
