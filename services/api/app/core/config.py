"""Typed, validated application settings loaded from environment variables.

Invalid or missing configuration raises at startup with a readable error instead of failing
later at first use. Production gets extra guard rails (no placeholder credentials, JSON logs,
HTTPS-only CORS origins).
"""

from __future__ import annotations

from functools import lru_cache
from math import ceil, isfinite
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.provider_urls import provider_url
from app.core.proxy_trust import parse_trusted_proxies

AppEnv = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["console", "json"]

PLACEHOLDER_MARKER = "change-me"
#: Largest ``Crawl-delay`` from robots.txt the crawler honours.
MAX_CRAWL_DELAY_SECONDS = 10.0
SQLALCHEMY_DRIVER = "postgresql+psycopg"


def _require_psycopg_driver(value: PostgresDsn | None) -> PostgresDsn | None:
    if value is not None and value.scheme != SQLALCHEMY_DRIVER:
        msg = f"must use the '{SQLALCHEMY_DRIVER}://' scheme (got '{value.scheme}://')"
        raise ValueError(msg)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Native runs from services/api pick up the repo-root .env; containers get real env vars.
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
    )

    app_name: str = "acs-api"
    app_env: AppEnv = "local"
    app_version: str = "0.1.0"
    log_level: LogLevel = "INFO"
    log_format: LogFormat = "json"

    database_url: PostgresDsn
    migration_database_url: PostgresDsn | None = None
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_pool_timeout_seconds: float = Field(default=2, gt=0, le=30)
    chat_setup_capacity: int = Field(default=8, ge=1, le=50)
    chat_admission_wait_seconds: float = Field(default=0.9, ge=0, le=2)

    redis_url: RedisDsn
    celery_broker_url: RedisDsn | None = None
    celery_result_backend: RedisDsn | None = None

    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    # --- ingress. Peers allowed to set X-Forwarded-For/-Proto (the reverse proxy); empty trusts
    # nobody. Only `python -m app.server` applies it (see app/core/proxy_trust.py).
    forwarded_allow_ips: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Uvicorn's CLI also reads these, outside this validation: declared only so they are refused.
    uvicorn_forwarded_allow_ips: str | None = None
    uvicorn_proxy_headers: str | None = None

    # --- web app / links in emails
    web_base_url: str = "http://localhost:3000"

    # --- sessions & tokens (docs/SECURITY.md §3)
    session_idle_days: int = Field(default=14, ge=1, le=90)
    session_absolute_days: int = Field(default=30, ge=1, le=365)
    session_touch_interval_seconds: int = Field(default=300, ge=0)
    verify_token_ttl_hours: int = Field(default=48, ge=1)
    reset_token_ttl_minutes: int = Field(default=30, ge=1)
    invitation_ttl_days: int = Field(default=7, ge=1, le=30)

    # --- Argon2id (OWASP baseline: 19 MiB, t=2, p=1)
    argon2_memory_kib: int = Field(default=19456, ge=8)
    argon2_time_cost: int = Field(default=2, ge=1)
    argon2_parallelism: int = Field(default=1, ge=1)

    # --- email delivery
    email_backend: Literal["smtp", "log"] = "log"
    email_from: str = "Support Platform <no-reply@example.com>"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False

    # --- rate limits (docs/API_SPEC.md §1.7); Redis fixed windows, fail closed
    rate_limit_login_ip_per_minute: int = 10
    rate_limit_login_ip_per_hour: int = 100
    rate_limit_login_email_per_minute: int = 5
    rate_limit_login_email_per_hour: int = 20
    login_lockout_failures: int = 5
    login_lockout_minutes: int = 15
    rate_limit_signup_per_hour: int = 10
    rate_limit_email_action_per_email_hour: int = 3
    rate_limit_email_action_per_ip_hour: int = 20
    rate_limit_invite_lookup_per_minute: int = 30
    rate_limit_search_per_minute: int = 60  # retrieval debugger, per user
    rate_limit_upload_per_minute: int = 60  # per organization

    # Static plan allowance until billing/entitlements ship (docs/ROADMAP.md AC2.7, Phase 6).
    chatbot_limit_per_org: int = Field(default=25, ge=1, le=1000)

    # --- private object storage for original files (S3 API; MinIO locally)
    s3_endpoint_url: str | None = None  # None = AWS S3
    s3_region: str = "us-east-1"
    s3_bucket: str = "acs-documents"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    storage_backend: Literal["s3", "memory"] = "s3"  # "memory" is for tests only

    # --- ingestion limits (docs/ROADMAP.md AC2.7: static limits until plans ship)
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    max_documents_per_chatbot: int = Field(default=500, ge=1)
    org_storage_limit_bytes: int = Field(default=2 * 1024**3, ge=1024)
    extract_max_pages: int = Field(default=500, ge=1)
    extract_max_chars: int = Field(default=5_000_000, ge=1000)
    docx_max_uncompressed_bytes: int = Field(default=100 * 1024 * 1024, ge=1024)

    # --- document parser isolation (docs/INGESTION.md): each parse runs in its own child process
    parser_wall_seconds: float = Field(default=60.0, gt=0, le=600)
    parser_cpu_seconds: int = Field(default=30, ge=1, le=600)
    parser_memory_bytes: int = Field(default=512 * 1024 * 1024, ge=256 * 1024 * 1024)
    parser_max_result_bytes: int = Field(default=32 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)

    # --- chunking (tokens are estimated: ~4 characters each, no tokenizer dependency)
    chunk_size_tokens: int = Field(default=350, ge=32, le=2000)
    chunk_overlap_tokens: int = Field(default=50, ge=0, le=500)

    # --- embeddings. "hash" is a deterministic local baseline (no network, no semantics beyond
    # shared vocabulary): fine for development and tests, refused in production.
    embedding_provider: Literal["hash", "openai_compatible"] = "hash"
    embedding_model: str = "hash-v1"
    embedding_dimensions: int = Field(default=1536, ge=8, le=2000)
    embedding_batch_size: int = Field(default=64, ge=1, le=512)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: SecretStr | None = None
    embedding_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    # Explicit development-only exception; never a private-network or container-host wildcard.
    allow_insecure_local_providers: bool = False

    # --- retrieval
    retrieval_candidates: int = Field(default=30, ge=1, le=200)
    retrieval_min_vector_score: float = Field(default=0.0, ge=0, le=1)

    # Chat is disabled until explicitly configured; demo is an offline fixture, never production.
    llm_provider: Literal["disabled", "demo", "openai_compatible"] = "disabled"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=60, ge=1, le=180)
    llm_retries: int = Field(default=2, ge=0, le=3)
    chat_context_messages: int = Field(default=12, ge=0, le=50)
    chat_input_token_budget: int = Field(default=16000, ge=1024, le=64000)
    chat_min_vector_score: float = Field(default=0.15, ge=0, le=1)
    chat_requests_per_minute: int = Field(default=60, ge=1)
    chat_concurrency_per_org: int = Field(default=3, ge=1, le=50)
    chat_monthly_token_limit: int = Field(default=2_000_000, ge=1)
    chat_monthly_cost_limit_usd: float = Field(default=25, gt=0)
    # Operator-maintained estimates per million tokens, keyed by allowlisted model id.
    chat_model_prices: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "gpt-4.1-mini": (0.40, 1.60),
            "gpt-4.1-nano": (0.10, 0.40),
            "gpt-4.1": (2.0, 8.0),
        }
    )
    widget_session_minutes: int = Field(default=15, ge=1, le=60)
    widget_messages_per_session: int = Field(default=30, ge=1, le=100)

    # --- background jobs
    ingest_max_attempts: int = Field(default=4, ge=1, le=10)
    ingest_retry_base_seconds: int = Field(default=5, ge=0)
    ingest_retry_max_seconds: int = Field(default=300, ge=0)
    ingest_stuck_after_seconds: int = Field(default=900, ge=30)
    ingest_sweep_interval_seconds: float = Field(default=120, ge=5, le=3600)
    # Heavy jobs (documents and crawls) one organization may run at once, and how long a job
    # that has to wait is first rescheduled for (doubling, capped).
    ingest_max_active_per_org: int = Field(default=1, ge=1, le=16)
    ingest_defer_seconds: float = Field(default=2, gt=0, le=15)
    # Celery task limits. Both stay below the broker's one-hour visibility timeout.
    ingest_soft_time_limit_seconds: int = Field(default=120, ge=2, le=3500)
    ingest_hard_time_limit_seconds: int = Field(default=180, ge=3, le=3540)
    crawl_max_task_seconds: int = Field(default=3300, ge=120, le=3540)  # operator maximum

    # --- website crawling (SafeFetcher)
    crawl_user_agent: str = "ACSBot/1.0 (+https://example.com/bot)"
    crawl_max_pages_limit: int = Field(default=200, ge=1)  # ceiling for a source's max_pages
    crawl_max_depth_limit: int = Field(default=5, ge=0)
    fetch_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    fetch_total_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    fetch_max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024)
    fetch_max_redirects: int = Field(default=5, ge=0, le=10)
    crawl_delay_seconds: float = Field(default=0.5, ge=0)
    crawl_allowed_ports: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [80, 443])

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _check_driver(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        return _require_psycopg_driver(value)

    @field_validator("crawl_allowed_ports", mode="before")
    @classmethod
    def _split_ports(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(item) for item in value.split(",") if item.strip()]
        return value

    @field_validator("forwarded_allow_ips", mode="before")
    @classmethod
    def _trusted_proxies(cls, value: object) -> list[str]:
        return parse_trusted_proxies(value)

    @model_validator(mode="after")
    def _no_uvicorn_proxy_overrides(self) -> Settings:
        for name in ("uvicorn_forwarded_allow_ips", "uvicorn_proxy_headers"):
            if getattr(self, name) is not None:
                raise ValueError(f"{name.upper()} is not supported; use FORWARDED_ALLOW_IPS")
        return self

    @field_validator("web_base_url")
    @classmethod
    def _strip_web_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parts = urlsplit(origin)
            if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path:
                msg = f"invalid CORS origin {origin!r}; expected scheme://host[:port]"
                raise ValueError(msg)
        return origins

    @model_validator(mode="after")
    def _check_chunking(self) -> Settings:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            msg = "CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _task_limits(self) -> Settings:
        if self.ingest_soft_time_limit_seconds >= self.ingest_hard_time_limit_seconds:
            raise ValueError(
                "INGEST_SOFT_TIME_LIMIT_SECONDS must be below INGEST_HARD_TIME_LIMIT_SECONDS"
            )
        return self

    @model_validator(mode="after")
    def _chat_guards(self) -> Settings:
        if any(
            not isfinite(a) or not isfinite(b) or a < 0 or b < 0
            for a, b in self.chat_model_prices.values()
        ):
            raise ValueError("CHAT_MODEL_PRICES must be nonnegative")
        if self.llm_provider == "openai_compatible" and (
            not self.llm_api_key or not self.llm_api_key.get_secret_value()
        ):
            raise ValueError("LLM_API_KEY is required")
        if self.is_production and self.llm_provider == "demo":
            raise ValueError("LLM_PROVIDER=demo is forbidden in production")
        return self

    @model_validator(mode="after")
    def _provider_guards(self) -> Settings:
        self.validate_provider_transport()
        return self

    def validate_provider_transport(self) -> None:
        """Also guard explicitly supplied/mutated settings at API/worker/adapter construction."""
        if self.allow_insecure_local_providers and self.app_env not in {"local", "test"}:
            raise ValueError("ALLOW_INSECURE_LOCAL_PROVIDERS is forbidden in staging/production")
        for name, active in [
            ("llm_base_url", self.llm_provider == "openai_compatible"),
            ("embedding_base_url", self.embedding_provider == "openai_compatible"),
        ]:
            if active:
                try:
                    canonical = provider_url(
                        getattr(self, name), allow_loopback_http=self.allow_insecure_local_providers
                    )
                except ValueError:
                    raise ValueError(
                        f"{name.upper()} must be an HTTPS provider URL with a safe host/port/path"
                    ) from None
                setattr(self, name, canonical)
        if self.embedding_provider == "openai_compatible" and (
            not self.embedding_api_key or not self.embedding_api_key.get_secret_value()
        ):
            raise ValueError("EMBEDDING_API_KEY is required")

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env != "production":
            return self
        problems: list[str] = []
        urls = {
            "DATABASE_URL": str(self.database_url),
            "MIGRATION_DATABASE_URL": str(self.migration_database_url or ""),
            "REDIS_URL": str(self.redis_url),
        }
        problems.extend(
            f"{name} contains a placeholder credential"
            for name, url in urls.items()
            if PLACEHOLDER_MARKER in url
        )
        if self.email_backend == "log":
            problems.append("EMAIL_BACKEND must be 'smtp' in production (log backend leaks tokens)")
        if not self.web_base_url.startswith("https://"):
            problems.append("WEB_BASE_URL must use https in production")
        if self.embedding_provider == "hash":
            problems.append("EMBEDDING_PROVIDER must not be 'hash' in production")
        if self.storage_backend != "s3":
            problems.append("STORAGE_BACKEND must be 's3' in production")
        if self.log_format != "json":
            problems.append("LOG_FORMAT must be 'json' in production")
        problems.extend(
            f"CORS origin {origin!r} must use https in production"
            for origin in self.cors_allowed_origins
            if not origin.startswith("https://")
        )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    @property
    def crawl_hard_time_limit_seconds(self) -> int:
        """Worst case for the page limit (robots, then delay + fetch + parse + one embedding
        request per page), capped by the operator maximum."""
        per_page = (
            max(self.crawl_delay_seconds, MAX_CRAWL_DELAY_SECONDS)
            + self.fetch_total_timeout_seconds
            + self.parser_wall_seconds
            + self.embedding_timeout_seconds
        )
        budget = self.fetch_total_timeout_seconds + self.crawl_max_pages_limit * per_page
        return min(ceil(budget), self.crawl_max_task_seconds)

    @property
    def crawl_soft_time_limit_seconds(self) -> int:
        hard = self.crawl_hard_time_limit_seconds
        return max(hard - 60, hard // 2)

    @property
    def broker_url(self) -> str:
        return str(self.celery_broker_url or self.redis_url)

    @property
    def result_backend_url(self) -> str:
        return str(self.celery_result_backend or self.redis_url)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


class MigrationSettings(BaseSettings):
    """Minimal settings for Alembic: only the database URL is needed to run migrations.

    Prefers MIGRATION_DATABASE_URL (schema-owner role); falls back to DATABASE_URL.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    migration_database_url: PostgresDsn | None = None
    database_url: PostgresDsn | None = None

    @field_validator("migration_database_url", "database_url")
    @classmethod
    def _check_driver(cls, value: PostgresDsn | None) -> PostgresDsn | None:
        return _require_psycopg_driver(value)

    @property
    def url(self) -> str:
        url = self.migration_database_url or self.database_url
        if url is None:
            msg = "Set MIGRATION_DATABASE_URL (or DATABASE_URL) to run migrations."
            raise ValueError(msg)
        return str(url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton. Tests construct `Settings(...)` directly instead."""
    return Settings()  # values come from the environment
