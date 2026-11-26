"""Alembic environment: runs migrations with the schema-owner database role."""

from __future__ import annotations

import os
from collections.abc import Collection, Mapping
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.runtime.migration import MigrationContext, MigrationInfo
from sqlalchemy import create_engine, pool

from app.core.config import MigrationSettings
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a database connection (`alembic upgrade head --sql`)."""
    context.configure(
        url=MigrationSettings().url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def refuse_deployed_downgrade(
    ctx: MigrationContext,
    step: MigrationInfo,
    heads: Collection[Any],
    run_args: Mapping[str, Any],
) -> None:
    """A downgrade drops columns and tables with their data (MIG-02, docs/RECOVERY.md).

    Runs after each step but inside the migration transaction, so refusing undoes all of it.
    """
    if (
        not step.is_upgrade
        and os.environ.get("APP_ENV") in {"staging", "production"}
        and os.environ.get("ALLOW_DESTRUCTIVE_DOWNGRADE") != "yes"
    ):
        raise RuntimeError(
            "Downgrade refused: it destroys data. Fix forward or restore a backup "
            "(docs/RECOVERY.md). To do it anyway, set ALLOW_DESTRUCTIVE_DOWNGRADE=yes."
        )


def run_migrations_online() -> None:
    engine = create_engine(MigrationSettings().url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            on_version_apply=refuse_deployed_downgrade,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
