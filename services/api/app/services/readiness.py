"""Readiness checks for the API's hard dependencies: Postgres (+pgvector, migrations) and Redis."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.logging import get_logger
from app.schemas.health import DependencyCheck

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.core.config import Settings

#: A check returns a short human-readable detail on success and raises on failure.
CheckFn = Callable[[], Awaitable[str | None]]

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
log = get_logger(__name__)


class DependencyNotReadyError(RuntimeError):
    """A dependency answered but is not in a usable state (e.g. migrations missing)."""


@cache
def expected_migration_heads() -> frozenset[str]:
    """Alembic head revision(s) shipped with this build."""
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    return frozenset(script.get_heads())


class ReadinessService:
    def __init__(
        self,
        checks: Mapping[str, CheckFn],
        *,
        timeout_seconds: float,
        expose_errors: bool,
    ) -> None:
        self._checks = dict(checks)
        self._timeout = timeout_seconds
        self._expose_errors = expose_errors

    async def run(self) -> dict[str, DependencyCheck]:
        names = list(self._checks)
        results = await asyncio.gather(*(self._run_one(name) for name in names))
        return dict(zip(names, results, strict=True))

    async def _run_one(self, name: str) -> DependencyCheck:
        started = time.perf_counter()

        def elapsed() -> float:
            return round((time.perf_counter() - started) * 1000, 2)

        try:
            detail = await asyncio.wait_for(self._checks[name](), timeout=self._timeout)
        except TimeoutError:
            log.warning("readiness.check_timeout", check=name, timeout_s=self._timeout)
            return DependencyCheck(status="error", latency_ms=elapsed(), detail="timeout")
        except Exception as exc:
            log.warning("readiness.check_failed", check=name, error=repr(exc))
            # Never leak connection strings/hosts in production responses; logs keep the detail.
            message = f"{type(exc).__name__}: {exc}" if self._expose_errors else type(exc).__name__
            return DependencyCheck(status="error", latency_ms=elapsed(), detail=message[:300])
        return DependencyCheck(status="ok", latency_ms=elapsed(), detail=detail)


def database_check(engine: AsyncEngine) -> CheckFn:
    async def check() -> str:
        async with engine.connect() as conn:
            version = await conn.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        if version is None:
            msg = "pgvector extension is not installed (run migrations)"
            raise DependencyNotReadyError(msg)
        return f"pgvector {version}"

    return check


def migrations_check(engine: AsyncEngine) -> CheckFn:
    async def check() -> str:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("SELECT to_regclass('public.alembic_version')"))
            if exists is None:
                msg = "database has not been migrated"
                raise DependencyNotReadyError(msg)
            current = set(
                (await conn.scalars(text("SELECT version_num FROM alembic_version"))).all()
            )
        expected = expected_migration_heads()
        if current != expected:
            msg = f"at revision {sorted(current)}, expected {sorted(expected)}"
            raise DependencyNotReadyError(msg)
        return f"revision {', '.join(sorted(current))}"

    return check


def redis_check(redis: Redis) -> CheckFn:
    async def check() -> str:
        info = await redis.info("server")
        return f"redis {info.get('redis_version', 'unknown')}"

    return check


def build_readiness_service(
    settings: Settings, engine: AsyncEngine, redis: Redis
) -> ReadinessService:
    return ReadinessService(
        {
            "database": database_check(engine),
            "migrations": migrations_check(engine),
            "redis": redis_check(redis),
        },
        timeout_seconds=settings.readiness_timeout_seconds,
        expose_errors=not settings.is_production,
    )
