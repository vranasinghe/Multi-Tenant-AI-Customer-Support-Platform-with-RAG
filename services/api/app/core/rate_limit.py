"""Redis fixed-window rate limiting and login lockout (docs/API_SPEC.md §1.7, SECURITY.md §3).

Keys hold a SHA-256 of the identifier (never raw emails/IPs). The limiter **fails closed**: if
Redis is unreachable the guarded endpoint answers 503 rather than silently dropping brute-force
protection.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from redis.exceptions import RedisError

from app.core.errors import ApiError
from app.core.logging import get_logger

if TYPE_CHECKING:
    from redis.asyncio import Redis

log = get_logger(__name__)


def _digest(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]


def rate_limited(retry_after: int, *, limit: int | None = None) -> ApiError:
    headers = {"Retry-After": str(max(1, retry_after))}
    if limit is not None:
        headers["RateLimit-Limit"] = str(limit)
        headers["RateLimit-Remaining"] = "0"
        headers["RateLimit-Reset"] = headers["Retry-After"]
    return ApiError(
        429,
        "rate_limited",
        "Too many requests",
        detail="Too many attempts. Please try again later.",
        headers=headers,
    )


def _unavailable() -> ApiError:
    return ApiError(503, "service_unavailable", "Service temporarily unavailable")


@dataclass(frozen=True)
class Limit:
    scope: str
    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def check(self, identifier: str, *limits: Limit) -> None:
        """Count one hit against each limit; raise 429 on the first one exceeded."""
        now = int(time.time())
        try:
            for item in limits:
                bucket = now // item.window_seconds
                key = f"rl:{item.scope}:{_digest(identifier)}:{item.window_seconds}:{bucket}"
                pipe = self._redis.pipeline()
                pipe.incr(key)
                pipe.expire(key, item.window_seconds + 1, nx=True)
                count, _ = await pipe.execute()
                if count > item.limit:
                    retry_after = item.window_seconds - (now % item.window_seconds)
                    log.warning("rate_limit.exceeded", scope=item.scope, limit=item.limit)
                    raise rate_limited(retry_after, limit=item.limit)
        except RedisError as exc:
            log.error("rate_limit.redis_unavailable", error=type(exc).__name__)
            raise _unavailable() from exc


class LoginGuard:
    """Per-account failure counter with a time-boxed lock (keyed by email hash, so unknown emails
    are throttled identically to real ones and enumeration stays impossible)."""

    def __init__(self, redis: Redis, *, threshold: int, lock_seconds: int) -> None:
        self._redis = redis
        self._threshold = threshold
        self._lock_seconds = lock_seconds

    def _keys(self, email: str) -> tuple[str, str]:
        digest = _digest(email)
        return f"login_fail:{digest}", f"login_lock:{digest}"

    async def assert_unlocked(self, email: str) -> None:
        _, lock_key = self._keys(email)
        try:
            ttl = await self._redis.ttl(lock_key)
        except RedisError as exc:
            raise _unavailable() from exc
        if ttl and ttl > 0:
            raise rate_limited(ttl)

    async def record_failure(self, email: str) -> bool:
        """Returns True when this failure triggered the lock."""
        fail_key, lock_key = self._keys(email)
        try:
            pipe = self._redis.pipeline()
            pipe.incr(fail_key)
            pipe.expire(fail_key, self._lock_seconds, nx=True)
            count, _ = await pipe.execute()
            if count >= self._threshold:
                await self._redis.set(lock_key, "1", ex=self._lock_seconds)
                await self._redis.delete(fail_key)
                return True
        except RedisError as exc:
            raise _unavailable() from exc
        return False

    async def clear(self, email: str) -> None:
        fail_key, lock_key = self._keys(email)
        try:
            await self._redis.delete(fail_key, lock_key)
        except RedisError as exc:
            log.error("login_guard.clear_failed", error=type(exc).__name__)
