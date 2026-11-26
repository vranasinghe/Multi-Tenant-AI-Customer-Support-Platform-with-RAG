"""Collaborators for ingestion workers (sync SQLAlchemy, object store, embedder, fetcher).

Celery tasks and tests build a ``Runtime`` once per process. Tenant isolation for workers: every
transaction starts by setting ``app.current_org_id`` from the job payload (``tenant_tx``); the
database then restricts the transaction to that organization via RLS, exactly like an API request.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.rag.chunking import ChunkingConfig
from app.rag.embeddings import Embedder, build_embedder
from app.rag.extract import Limits
from app.rag.parser_runner import ParserLimits, ParserRunner
from app.rag.safe_fetch import SafeFetcher
from app.rag.storage import ObjectStore, build_object_store

if TYPE_CHECKING:
    import uuid

    from sqlalchemy import Engine

    from app.core.config import Settings


@dataclass
class Runtime:
    settings: Settings
    session_factory: sessionmaker[Session]
    store: ObjectStore
    embedder: Embedder
    fetcher: SafeFetcher
    parser: ParserRunner
    engine: Engine | None = None

    @property
    def limits(self) -> Limits:
        s = self.settings
        return Limits(
            max_pages=s.extract_max_pages,
            max_chars=s.extract_max_chars,
            max_uncompressed_bytes=s.docx_max_uncompressed_bytes,
        )

    @property
    def chunking(self) -> ChunkingConfig:
        return ChunkingConfig(self.settings.chunk_size_tokens, self.settings.chunk_overlap_tokens)

    @contextmanager
    def tenant_tx(self, org_id: uuid.UUID) -> Iterator[Session]:
        """One short transaction scoped to ``org_id`` (commits on success, rolls back on error)."""
        with self.session_factory() as session, session.begin():
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_id)}
            )
            yield session


def build_fetcher(settings: Settings) -> SafeFetcher:
    return SafeFetcher(
        user_agent=settings.crawl_user_agent,
        timeout=settings.fetch_timeout_seconds,
        total_timeout=settings.fetch_total_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
        allowed_ports=settings.crawl_allowed_ports,
    )


def build_parser(settings: Settings) -> ParserRunner:
    return ParserRunner(
        ParserLimits(
            wall_seconds=settings.parser_wall_seconds,
            cpu_seconds=settings.parser_cpu_seconds,
            memory_bytes=settings.parser_memory_bytes,
            # The approved upload and fetch limits; storage reads allow the same headroom.
            max_input_bytes=max(settings.upload_max_bytes + 1024, settings.fetch_max_bytes),
            max_result_bytes=settings.parser_max_result_bytes,
            require_containment=settings.app_env in {"staging", "production"},
        )
    )


def build_runtime(settings: Settings) -> Runtime:
    engine = create_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        connect_args={"application_name": f"{settings.app_name}-worker", "connect_timeout": 5},
    )
    return Runtime(
        settings=settings,
        session_factory=sessionmaker(engine, expire_on_commit=False),
        store=build_object_store(settings),
        embedder=build_embedder(settings),
        fetcher=build_fetcher(settings),
        parser=build_parser(settings),
        engine=engine,
    )


_lock = threading.Lock()
_runtime: Runtime | None = None


def get_runtime() -> Runtime:
    """The process-wide runtime (built lazily from settings; tests may install their own)."""
    global _runtime  # noqa: PLW0603
    with _lock:
        if _runtime is None:
            from app.core.config import get_settings  # noqa: PLC0415

            _runtime = build_runtime(get_settings())
        return _runtime


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime  # noqa: PLW0603
    with _lock:
        _runtime = runtime
