from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import MigrationSettings
from tests.conftest import make_settings

PROD_DB = "postgresql+psycopg://platform_app:s3cret@db.internal:5432/chatbot"
PROD_REDIS = "rediss://cache.internal:6380/0"
PROD_EXTRAS: dict[str, Any] = {
    "email_backend": "smtp",
    "web_base_url": "https://app.example.com",
    "embedding_provider": "openai_compatible",
    "embedding_api_key": "test-key",
}


def test_valid_settings_and_derived_celery_urls() -> None:
    settings = make_settings()

    assert settings.app_env == "test"
    assert settings.broker_url == "redis://localhost:6379/0"
    assert settings.result_backend_url == "redis://localhost:6379/0"


def test_explicit_celery_urls_win() -> None:
    settings = make_settings(
        celery_broker_url="redis://localhost:6379/1",
        celery_result_backend="redis://localhost:6379/2",
    )

    assert settings.broker_url == "redis://localhost:6379/1"
    assert settings.result_backend_url == "redis://localhost:6379/2"


def test_database_url_requires_psycopg_driver() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+psycopg"):
        make_settings(database_url="postgresql://u:p@localhost:5432/db")


def test_missing_required_values_are_reported() -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(database_url=None, redis_url=None)

    fields = {err["loc"][0] for err in exc_info.value.errors()}
    assert {"database_url", "redis_url"} <= fields


def test_log_level_is_case_insensitive() -> None:
    assert make_settings(log_level="debug").log_level == "DEBUG"


def test_cors_origins_parse_from_comma_separated_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000, https://app.example.com/")

    settings = make_settings()

    assert settings.cors_allowed_origins == ["http://localhost:3000", "https://app.example.com"]


@pytest.mark.parametrize("origin", ["localhost:3000", "https://app.example.com/path", "ftp://x.y"])
def test_invalid_cors_origin_rejected(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS origin"):
        make_settings(cors_allowed_origins=[origin])


def test_production_accepts_safe_configuration() -> None:
    settings = make_settings(
        app_env="production",
        log_format="json",
        database_url=PROD_DB,
        redis_url=PROD_REDIS,
        cors_allowed_origins=["https://app.example.com"],
        **PROD_EXTRAS,
    )

    assert settings.is_production


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"database_url": "postgresql+psycopg://u:change-me@db:5432/x"}, "placeholder"),
        ({"log_format": "console"}, "LOG_FORMAT"),
        ({"cors_allowed_origins": ["http://app.example.com"]}, "https"),
        ({"email_backend": "log"}, "EMAIL_BACKEND"),
        ({"web_base_url": "http://app.example.com"}, "WEB_BASE_URL"),
    ],
)
def test_production_guards(overrides: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "app_env": "production",
        "log_format": "json",
        "database_url": PROD_DB,
        "redis_url": PROD_REDIS,
        **PROD_EXTRAS,
    }
    values.update(overrides)

    with pytest.raises(ValidationError, match=message):
        make_settings(**values)


def test_migration_settings_prefer_owner_url() -> None:
    urls: dict[str, Any] = {
        "migration_database_url": "postgresql+psycopg://owner:x@localhost:5432/db",
        "database_url": "postgresql+psycopg://app:y@localhost:5432/db",
    }
    settings = MigrationSettings(_env_file=None, **urls)

    assert settings.url.startswith("postgresql+psycopg://owner:")


def test_migration_settings_require_a_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="MIGRATION_DATABASE_URL"):
        _ = MigrationSettings(_env_file=None).url
