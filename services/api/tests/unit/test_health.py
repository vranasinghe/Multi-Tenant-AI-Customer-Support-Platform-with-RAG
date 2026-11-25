from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_readiness_service
from app.services.readiness import ReadinessService


async def _ok() -> str:
    return "fine"


async def _boom() -> str:
    msg = "connection refused to db.internal"
    raise ConnectionError(msg)


async def _slow() -> str:
    await asyncio.sleep(1)
    return "too late"


def _override(app: FastAPI, service: ReadinessService) -> None:
    app.dependency_overrides[get_readiness_service] = lambda: service


def test_liveness(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "acs-api", "version": "0.1.0"}


def test_readiness_ok(app: FastAPI, client: TestClient) -> None:
    _override(
        app,
        ReadinessService({"database": _ok, "redis": _ok}, timeout_seconds=1, expose_errors=True),
    )

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["database"]["detail"] == "fine"


def test_readiness_degraded_returns_503(app: FastAPI, client: TestClient) -> None:
    _override(
        app,
        ReadinessService({"database": _boom, "redis": _ok}, timeout_seconds=1, expose_errors=True),
    )

    response = client.get("/readyz")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["database"]["detail"].startswith("ConnectionError")
    assert body["checks"]["redis"]["status"] == "ok"


async def test_readiness_check_timeout_is_reported() -> None:
    service = ReadinessService({"slow": _slow}, timeout_seconds=0.05, expose_errors=True)

    result = await service.run()

    assert result["slow"].status == "error"
    assert result["slow"].detail == "timeout"


async def test_readiness_hides_error_messages_when_not_exposed() -> None:
    service = ReadinessService({"database": _boom}, timeout_seconds=1, expose_errors=False)

    result = await service.run()

    assert result["database"].detail == "ConnectionError"


async def test_readiness_runs_checks_concurrently() -> None:
    async def wait() -> str:
        await asyncio.sleep(0.1)
        return "ok"

    service = ReadinessService(
        {"a": wait, "b": wait, "c": wait}, timeout_seconds=1, expose_errors=True
    )
    loop = asyncio.get_running_loop()

    started = loop.time()
    await service.run()

    assert loop.time() - started < 0.25
