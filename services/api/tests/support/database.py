"""Throwaway migrated database for integration tests.

Each pytest session creates ``chatbot_test_<random>`` through the schema-owner role, runs the real
Alembic migrations against it, and drops it afterwards, so tests never touch development data.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

from app.services.readiness import ALEMBIC_INI


@dataclass(frozen=True)
class TestDatabase:
    __test__ = False  # not a pytest test class

    name: str
    owner_url: URL  # schema owner: superuser-like in dev/CI; used for seeding and inspection
    app_url: URL  # unprivileged runtime role: subject to RLS


def _urls_from_env() -> tuple[URL, URL]:
    owner = os.environ.get("MIGRATION_DATABASE_URL")
    app = os.environ.get("DATABASE_URL")
    if not owner or not app:
        pytest.skip("MIGRATION_DATABASE_URL and DATABASE_URL are required for integration tests")
    return make_url(owner), make_url(app)


@pytest.fixture(scope="session")
def test_database() -> Iterator[TestDatabase]:
    owner_base, app_base = _urls_from_env()
    name = f"chatbot_test_{secrets.token_hex(4)}"
    admin = create_engine(owner_base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))

    owner_url = owner_base.set(database=name)
    app_url = app_base.set(database=name)
    owner_name = owner_url.username

    prep = create_engine(owner_url, isolation_level="AUTOCOMMIT")
    with prep.connect() as conn:
        # Same grants the Docker init / CI role script apply to the real database.
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{name}" TO "{app_url.username}"'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA public TO "{app_url.username}"'))
        conn.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner_name}" IN SCHEMA public '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{app_url.username}"'
            )
        )
        conn.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner_name}" IN SCHEMA public '
                f'GRANT USAGE, SELECT ON SEQUENCES TO "{app_url.username}"'
            )
        )
    prep.dispose()

    previous = os.environ.get("MIGRATION_DATABASE_URL")
    os.environ["MIGRATION_DATABASE_URL"] = owner_url.render_as_string(hide_password=False)
    try:
        command.upgrade(Config(str(ALEMBIC_INI)), "head")
    finally:
        if previous is None:
            os.environ.pop("MIGRATION_DATABASE_URL", None)
        else:
            os.environ["MIGRATION_DATABASE_URL"] = previous

    try:
        yield TestDatabase(name=name, owner_url=owner_url, app_url=app_url)
    finally:
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()
