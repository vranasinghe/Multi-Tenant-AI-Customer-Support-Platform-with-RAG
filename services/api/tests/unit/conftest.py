"""Unit tests must not depend on the ambient environment (containers export real DB URLs)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_ambient_database_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MIGRATION_DATABASE_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "CORS_ALLOWED_ORIGINS",
        "LOG_FORMAT",
    ):
        monkeypatch.delenv(name, raising=False)
