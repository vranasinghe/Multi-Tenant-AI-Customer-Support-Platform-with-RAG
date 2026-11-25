"""Exercise rollback/upgrade only in the fixture's throwaway database, never development data."""

from __future__ import annotations

import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect

from app.services.readiness import ALEMBIC_INI
from tests.support.database import TestDatabase

pytestmark = pytest.mark.integration


def test_chat_migration_roundtrip(
    test_database: TestDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert test_database.name.startswith("chatbot_test_")
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", test_database.owner_url.render_as_string(hide_password=False)
    )

    def migrate(target: str, direction: str) -> None:
        # Run CLI migrations in their own process so Alembic logging cannot disable app loggers.
        subprocess.run(  # noqa: S603  # fixed interpreter/CLI; target values are test constants
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), direction, target],
            check=True,
            capture_output=True,
        )

    engine = create_engine(test_database.owner_url)
    try:
        migrate("0004", "downgrade")
        assert "conversations" not in inspect(engine).get_table_names()
    finally:
        migrate("head", "upgrade")
        engine.dispose()
    engine = create_engine(test_database.owner_url)
    try:
        assert {"conversations", "messages", "widget_sessions", "chat_usage"} <= set(
            inspect(engine).get_table_names()
        )
    finally:
        engine.dispose()
