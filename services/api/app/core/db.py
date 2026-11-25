"""Database engines: async for the API; workers and Alembic use sync engines (ADR-007)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create the async engine. Connections are opened lazily, so startup never blocks on the DB."""
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        pool_pre_ping=True,
        hide_parameters=True,  # database failures must not put prompts/messages into logs
        connect_args={"application_name": settings.app_name, "connect_timeout": 5},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
