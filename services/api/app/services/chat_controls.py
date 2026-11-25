"""Redis leases (atomic, expiring) and serialized Postgres monthly usage reservations."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import anyio
from redis.exceptions import RedisError
from sqlalchemy import func, select, text

from app.core.errors import ApiError
from app.models.conversations import ChatUsage
from app.models.identity import utcnow

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import Settings

_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('EXISTS', KEYS[2]) == 1 then return 0 end
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then return 0 end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[5])
redis.call('SET', KEYS[2], ARGV[3], 'EX', ARGV[5])
return 1
"""
_RELEASE = """
redis.call('ZREM', KEYS[1], ARGV[1])
if redis.call('GET', KEYS[2]) == ARGV[1] then redis.call('DEL', KEYS[2]) end
return 1
"""


@dataclass(frozen=True)
class Lease:
    org_key: str
    conversation_key: str
    token: str

    async def release(self, redis: Redis) -> None:
        await redis.eval(_RELEASE, 2, self.org_key, self.conversation_key, self.token)


async def acquire(
    redis: Redis, org_id: uuid.UUID, conversation_id: uuid.UUID, settings: Settings
) -> Lease:
    lease = Lease(
        f"chat:{{{org_id}}}:active",
        f"chat:{{{org_id}}}:conversation:{conversation_id}",
        uuid.uuid4().hex,
    )
    ttl = int(settings.embedding_timeout_seconds + settings.llm_timeout_seconds) + 90
    try:
        accepted = await redis.eval(
            _ACQUIRE,
            2,
            lease.org_key,
            lease.conversation_key,
            time.time(),
            time.time() + ttl,
            lease.token,
            settings.chat_concurrency_per_org,
            ttl,
        )
    except asyncio.CancelledError:
        # The script may already have run before cancellation of the socket read.
        with anyio.CancelScope(shield=True):
            # TTL is the fail-closed fallback when Redis is unavailable.
            with contextlib.suppress(RedisError):
                await lease.release(redis)
        raise
    except RedisError:
        raise ApiError(503, "chat_unavailable", "Chat temporarily unavailable") from None
    if not accepted:
        raise ApiError(
            429,
            "chat_busy",
            "A conversation is already running or the workspace is busy",
            headers={"Retry-After": "2"},
        )
    return lease


def cost(input_tokens: int, output_tokens: int, prices: tuple[float, float]) -> Decimal:
    return (
        Decimal(input_tokens) * Decimal(str(prices[0]))
        + Decimal(output_tokens) * Decimal(str(prices[1]))
    ) / 1_000_000


async def reserve(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    model: str,
    tokens: int,
    amount: Decimal,
    settings: Settings,
) -> None:
    # All API instances serialize reservation checks for this org in the same database.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"chat-quota:{org_id}"},
    )
    period = utcnow().strftime("%Y-%m")
    used, spent = (
        await db.execute(
            select(
                func.coalesce(func.sum(ChatUsage.charged_tokens), 0),
                func.coalesce(func.sum(ChatUsage.estimated_cost_usd), 0),
            ).where(ChatUsage.org_id == org_id, ChatUsage.period == period)
        )
    ).one()
    if used + tokens > settings.chat_monthly_token_limit or spent + amount > Decimal(
        str(settings.chat_monthly_cost_limit_usd)
    ):
        raise ApiError(429, "quota_exceeded", "This workspace has reached its chat usage limit")
    db.add(
        ChatUsage(
            id=message_id,
            org_id=org_id,
            conversation_id=conversation_id,
            model=model,
            period=period,
            charged_tokens=tokens,
            estimated_cost_usd=amount,
        )
    )
