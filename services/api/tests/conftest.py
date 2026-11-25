"""Shared fixtures.

Unit tests never touch real services: they build settings explicitly and override the readiness
service. Integration tests (marked `integration`) read real connection settings from the
environment — see docs/DEVELOPMENT.md.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Importing app.workers.celery_app builds settings from the environment. Precedence:
# real env vars (containers, CI) > repo-root .env (native runs) > harmless unit-test defaults.
_ROOT_ENV_PATH = next(
    (parent / ".env" for parent in Path(__file__).resolve().parents if (parent / ".env").is_file()),
    None,
)  # absent inside the dev container (only services/api is mounted); env vars are set there
_ROOT_ENV = dotenv_values(_ROOT_ENV_PATH) if _ROOT_ENV_PATH else {}
_FALLBACKS = {
    "DATABASE_URL": "postgresql+psycopg://platform_app:test@localhost:5432/chatbot_test",
    "REDIS_URL": "redis://localhost:6379/0",
}
for _key, _fallback in _FALLBACKS.items():
    os.environ.setdefault(_key, _ROOT_ENV.get(_key) or _fallback)

if sys.platform == "win32":
    # Async psycopg cannot run on Windows' default Proactor loop. Containers/CI are Linux and
    # unaffected; `uvicorn --reload` already selects a Selector loop on Windows.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

pytest_plugins = ["tests.support.database"]  # provides the `test_database` fixture

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "log_format": "console",
        "log_level": "WARNING",
        "database_url": "postgresql+psycopg://platform_app:test@localhost:5432/chatbot_test",
        "redis_url": "redis://localhost:6379/0",
        "llm_provider": "disabled",  # isolate tests from an operator's demo/live provider env
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
