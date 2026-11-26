"""A downgrade drops data (MIG-02): deployed environments refuse it unless asked twice."""

from __future__ import annotations

import subprocess
import sys

import pytest

from app.services.readiness import ALEMBIC_INI
from tests.integration.test_chat_migration import database, query, revision
from tests.support.database import TestDatabase

__all__ = ["database"]

pytestmark = pytest.mark.integration


def alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed interpreter/CLI; arguments are test constants
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        check=False,  # refusal is one of the outcomes
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_a_deployed_environment_refuses_a_downgrade_without_changing_anything(
    database: TestDatabase, monkeypatch: pytest.MonkeyPatch, app_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)
    tables = "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"
    before = query(database, tables)

    result = alembic("downgrade", "0005")

    assert result.returncode != 0
    assert "ALLOW_DESTRUCTIVE_DOWNGRADE" in result.stderr
    assert revision(database) == "0007" and query(database, tables) == before
    assert alembic("upgrade", "head").returncode == 0  # moving forward is never blocked


def test_a_deliberate_downgrade_is_still_possible(
    database: TestDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DESTRUCTIVE_DOWNGRADE", "yes")

    result = alembic("downgrade", "0006")

    assert result.returncode == 0, result.stderr
    assert revision(database) == "0006"
