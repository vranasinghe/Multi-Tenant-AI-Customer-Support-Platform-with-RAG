"""Helpers for ingestion integration tests: a sync runtime on the test database and a job runner."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.rag.crawl_job import run_crawl_job
from app.rag.embeddings import Embedder, HashingEmbedder
from app.rag.errors import TransientIngestionError
from app.rag.parser_runner import ParserRunner
from app.rag.pipeline import run_document_job
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime, build_fetcher, build_parser
from app.rag.safe_fetch import SafeFetcher
from app.rag.storage import ObjectStore


def make_runtime(
    settings: Settings,
    engine: Engine,
    store: ObjectStore,
    *,
    embedder: Embedder | None = None,
    fetcher: SafeFetcher | None = None,
    parser: ParserRunner | None = None,
) -> Runtime:
    return Runtime(
        settings=settings,
        session_factory=sessionmaker(engine, expire_on_commit=False),
        store=store,
        embedder=embedder or HashingEmbedder(settings.embedding_model),
        fetcher=fetcher or build_fetcher(settings),
        parser=parser or build_parser(settings),
        engine=engine,
    )


def run_jobs(rt: Runtime, queue: RecordingJobQueue) -> list[str]:
    """Execute queued jobs in order like a worker would. Transient failures yield ``retry``."""
    outcomes: list[str] = []
    while queue.jobs:
        org_id, job_id, kind = queue.jobs.pop(0)
        runner = run_document_job if kind == "process_document" else run_crawl_job
        try:
            outcomes.append(runner(rt, org_id, job_id))
        except TransientIngestionError:
            outcomes.append("retry")
    return outcomes


class FlakyEmbedder:
    """Fails with a transient error for the first ``failures`` calls, then delegates."""

    def __init__(self, failures: int, inner: Embedder | None = None) -> None:
        self.inner = inner or HashingEmbedder()
        self.model_id = self.inner.model_id
        self.dimensions = self.inner.dimensions
        self.failures = failures
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls <= self.failures:
            raise TransientIngestionError("embedding_failed", "simulated outage")
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)


def scalar(engine: Engine, statement: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(statement), params).scalar()


def rows(engine: Engine, statement: str, **params: Any) -> list[Any]:
    with engine.begin() as conn:
        return list(conn.execute(text(statement), params).all())


def as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
