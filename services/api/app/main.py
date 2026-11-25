"""ASGI application factory.

Run with: `uvicorn app.main:create_app --factory` (no module-level app, so importing this module
never requires configuration — tests build apps with explicit settings).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, v1, widget_chat, widget_install
from app.core.chat_body_limit import ChatBodyLimit
from app.core.config import Settings, get_settings
from app.core.csrf import CsrfMiddleware
from app.core.db import create_engine, create_session_factory
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import LoginGuard, RateLimiter
from app.core.redis import create_redis
from app.core.request_context import RequestContextMiddleware
from app.core.security import PasswordService
from app.integrations.email import EmailSender, build_email_sender
from app.integrations.llm import ChatProvider, build_chat_provider
from app.rag.embeddings import Embedder, build_embedder
from app.rag.queue import JobQueue, build_job_queue
from app.rag.runtime import build_fetcher
from app.rag.safe_fetch import SafeFetcher
from app.rag.storage import ObjectStore, build_object_store
from app.services.chat_work import ChatWork
from app.services.container import AppServices
from app.services.readiness import build_readiness_service

log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    email_sender: EmailSender | None = None,
    object_store: ObjectStore | None = None,
    job_queue: JobQueue | None = None,
    embedder: Embedder | None = None,
    fetcher: SafeFetcher | None = None,
    chat_provider: ChatProvider | None = None,
) -> FastAPI:
    """Build the ASGI app. Keyword overrides let tests capture mail, storage and jobs."""
    settings = settings or get_settings()
    settings.validate_provider_transport()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        redis = create_redis(settings)
        app.state.engine = engine
        app.state.redis = redis
        app.state.readiness = build_readiness_service(settings, engine, redis)
        app.state.services = AppServices(
            settings=settings,
            session_factory=create_session_factory(engine),
            redis=redis,
            passwords=PasswordService(
                memory_kib=settings.argon2_memory_kib,
                time_cost=settings.argon2_time_cost,
                parallelism=settings.argon2_parallelism,
            ),
            limiter=RateLimiter(redis),
            login_guard=LoginGuard(
                redis,
                threshold=settings.login_lockout_failures,
                lock_seconds=settings.login_lockout_minutes * 60,
            ),
            email_sender=email_sender or build_email_sender(settings),
            store=object_store or build_object_store(settings),
            jobs=job_queue or build_job_queue(settings),
            embedder=embedder or build_embedder(settings),
            fetcher=fetcher or build_fetcher(settings),
            chat_provider=chat_provider or build_chat_provider(settings),
            chat_work=ChatWork(settings),
        )
        log.info("api.startup", environment=settings.app_env, version=settings.app_version)
        try:
            yield
        finally:
            await redis.aclose()
            await engine.dispose()
            log.info("api.shutdown")

    expose_docs = not settings.is_production
    app = FastAPI(
        title="AI Support Platform API",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_docs else None,
    )
    app.state.settings = settings

    register_exception_handlers(app)
    app.include_router(widget_install.router)
    app.include_router(health.router)
    app.include_router(v1.router, prefix="/api/v1")
    app.include_router(widget_chat.router, prefix="/public/v1")

    # Middleware order (last added = outermost): request-id → CORS → CSRF → routes.
    app.add_middleware(CsrfMiddleware, allowed_origins=settings.cors_allowed_origins)
    app.add_middleware(ChatBodyLimit)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Content-Type",
                "X-Request-ID",
                "X-Requested-With",
                "Idempotency-Key",
                "Authorization",
            ],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )
    # Added last => outermost: every response (including CORS and errors) gets a request id.
    app.add_middleware(RequestContextMiddleware)
    return app
