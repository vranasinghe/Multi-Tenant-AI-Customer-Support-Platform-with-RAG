from __future__ import annotations

import json
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.logging import configure_logging
from app.core.request_context import resolve_request_id


@pytest.fixture
def app_with_probe_routes(app: FastAPI) -> FastAPI:
    @app.get("/_probe/state")
    async def state(request: Request) -> dict[str, str]:
        return {"request_id": request.state.request_id}

    @app.get("/_probe/crash")
    async def crash() -> None:
        msg = "kaboom"
        raise RuntimeError(msg)

    return app


@pytest.fixture
def probe_client(app_with_probe_routes: FastAPI) -> TestClient:
    return TestClient(app_with_probe_routes, raise_server_exceptions=False)


def test_generates_request_id_when_absent(client: TestClient) -> None:
    response = client.get("/healthz")

    request_id = response.headers["x-request-id"]
    assert uuid.UUID(request_id)


def test_echoes_valid_incoming_request_id(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "web-req.1234_abcd"})

    assert response.headers["x-request-id"] == "web-req.1234_abcd"


@pytest.mark.parametrize("bad", ["short", "a" * 129, "has space inside", "<script>alert</script>"])
def test_replaces_malformed_request_id(client: TestClient, bad: str) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": bad})

    assert response.headers["x-request-id"] != bad
    assert uuid.UUID(response.headers["x-request-id"])


def test_request_id_available_to_handlers(probe_client: TestClient) -> None:
    response = probe_client.get("/_probe/state", headers={"X-Request-ID": "abc12345"})

    assert response.json() == {"request_id": "abc12345"}


def test_unhandled_exception_becomes_problem_response(probe_client: TestClient) -> None:
    response = probe_client.get("/_probe/crash")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "internal_error"
    assert "kaboom" not in json.dumps(body)  # no internals leaked
    assert body["request_id"] == response.headers["x-request-id"]


def test_access_log_line_is_structured_and_carries_request_id(
    probe_client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("INFO", "json")

    probe_client.get("/_probe/state", headers={"X-Request-ID": "trace-me-123"})

    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    access = [line for line in lines if line.get("event") == "request.completed"]
    assert access, f"no access log in {lines}"
    entry = access[-1]
    assert entry["request_id"] == "trace-me-123"
    assert entry["status"] == 200
    assert entry["path"] == "/_probe/state"
    assert entry["level"] == "info"
    assert "timestamp" in entry
    assert entry["duration_ms"] >= 0


def test_resolve_request_id_rules() -> None:
    assert resolve_request_id("valid-id-1") == "valid-id-1"
    assert resolve_request_id(None) != resolve_request_id(None)
