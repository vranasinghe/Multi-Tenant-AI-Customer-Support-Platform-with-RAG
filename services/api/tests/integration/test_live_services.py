"""Integration tests against real Postgres (migrated) and Redis.

Run with services up and env configured (docker compose or CI service containers):
    uv run pytest -m integration
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import structlog
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings, get_settings
from app.main import create_app
from app.workers.celery_app import celery_app
from app.workers.tasks.system import ping

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def live_client(live_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(live_settings)) as client:
        yield client


def test_readyz_reports_all_dependencies_ok(live_client: TestClient) -> None:
    response = live_client.get("/readyz")

    body = response.json()
    assert response.status_code == 200, body
    assert body["status"] == "ok"
    assert body["checks"]["database"]["detail"].startswith("pgvector ")
    assert body["checks"]["migrations"]["status"] == "ok"
    assert body["checks"]["redis"]["detail"].startswith("redis ")


def test_runtime_role_is_unprivileged_and_extensions_exist(live_settings: Settings) -> None:
    engine = create_engine(str(live_settings.database_url))
    try:
        with engine.connect() as conn:
            superuser, bypass_rls = conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            ).one()
            extensions = set(conn.scalars(text("SELECT extname FROM pg_extension")).all())
    finally:
        engine.dispose()

    # RLS (docs/DATABASE.md §4) only protects us if the runtime role cannot bypass it.
    assert superuser is False
    assert bypass_rls is False
    assert {"vector", "citext", "pg_trgm", "pgcrypto"} <= extensions


def test_tenant_context_helpers_are_transaction_scoped(live_settings: Settings) -> None:
    org_id = "0193a5b2-7c1d-7e4f-8a90-123456789abc"
    engine = create_engine(str(live_settings.database_url))
    try:
        with engine.begin() as conn:
            assert conn.scalar(text("SELECT app.current_org_id()")) is None
            conn.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"), {"org": org_id}
            )
            assert str(conn.scalar(text("SELECT app.current_org_id()"))) == org_id
        with engine.connect() as conn:  # new transaction: setting must not leak
            assert conn.scalar(text("SELECT app.current_org_id()")) is None
    finally:
        engine.dispose()


def test_celery_round_trip_through_redis_propagates_request_id() -> None:
    with start_worker(celery_app, pool="solo", perform_ping_check=False, loglevel="WARNING"):
        structlog.contextvars.bind_contextvars(request_id="integration-req-1")
        try:
            result = ping.delay().get(timeout=20)
        finally:
            structlog.contextvars.clear_contextvars()

    assert result == {"pong": "ok", "request_id": "integration-req-1"}
