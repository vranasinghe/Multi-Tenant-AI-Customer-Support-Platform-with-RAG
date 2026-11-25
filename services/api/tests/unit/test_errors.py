from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/does-not-exist", headers={"X-Request-ID": "req-404-test"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://docs.example.com/errors/not_found",
        "title": "Not Found",
        "status": 404,
        "code": "not_found",
        "request_id": "req-404-test",
    }


def test_wrong_method_returns_405_problem(client: TestClient) -> None:
    response = client.post("/healthz")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_validation_errors_list_fields(app: FastAPI) -> None:
    @app.get("/_probe/items")
    async def items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    response = TestClient(app).get("/_probe/items", params={"limit": "lots"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["field"] == "query.limit"
    assert body["errors"][0]["code"] == "int_parsing"


def test_docs_disabled_in_production() -> None:
    from app.main import create_app
    from tests.conftest import make_settings

    prod = make_settings(
        app_env="production",
        log_format="json",
        database_url="postgresql+psycopg://a:b@db:5432/x",
        redis_url="redis://cache:6379/0",
        email_backend="smtp",
        web_base_url="https://app.example.com",
        embedding_provider="openai_compatible",
        embedding_api_key="test-key",
    )
    response = TestClient(create_app(prod)).get("/openapi.json")

    assert response.status_code == 404
