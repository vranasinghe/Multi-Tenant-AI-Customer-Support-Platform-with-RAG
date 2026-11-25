"""Shared async Redis client (cache, rate limits, quota counters in later phases)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    from app.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        str(settings.redis_url),
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
        decode_responses=True,
    )
