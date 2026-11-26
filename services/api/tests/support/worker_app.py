"""The production Celery app and tasks for real-worker tests (``celery -A tests.support.worker_app``).

Only collaborators are replaced, never task, queue or pipeline code:

* originals live in a shared directory, or in the real object storage (``TEST_OBJECT_STORE=s3``);
  a page containing ``STOREHANGBEFORE``/``STOREHANGAFTER`` stops its first upload there;
* the (real, limited) parser child misbehaves for documents that ask it to, unless
  ``TEST_PARSER=production``;
* the embedder stalls or fails for the markers listed on ``MarkedEmbedder``;
* with ``TEST_SITE_PORT``, ``site.test`` resolves to the test's own loopback web server. Every
  other host keeps the production SSRF resolution and address policy.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from celery.exceptions import SoftTimeLimitExceeded

from app.core.config import Settings, get_settings
from app.rag import runtime
from app.rag.embeddings import HashingEmbedder
from app.rag.errors import TransientIngestionError
from app.rag.parser_runner import ParserRunner
from app.rag.safe_fetch import SafeFetcher, is_public_ip, system_resolver
from app.rag.storage import ObjectStore, S3ObjectStore
from app.workers.celery_app import celery_app
from tests.support.file_store import FileObjectStore

__all__ = ["celery_app"]


def _first_time(name: str) -> bool:
    """True once per test run for ``name``, across every pool process."""
    try:
        os.close(os.open(Path(os.environ["TEST_OBJECT_DIR"]).parent / name, os.O_CREAT | os.O_EXCL))
    except FileExistsError:
        return False
    return True


def _forever() -> None:
    while True:
        time.sleep(0.1)


class MarkedEmbedder(HashingEmbedder):
    """``HOSTILE-IGNORE-SOFT-LIMIT`` outlives the soft limit; ``SLOWEMBED`` is ended by it;
    ``FAILEMBED`` fails transiently; the first ``HOLDEMBED`` waits for the test to release it."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        joined = " ".join(texts)
        if "HOSTILE-IGNORE-SOFT-LIMIT" in joined:
            while True:  # only the hard limit can end this task
                try:
                    _forever()
                except SoftTimeLimitExceeded:
                    continue
        if "SLOWEMBED" in joined:
            _forever()
        if "FAILEMBED" in joined:
            raise TransientIngestionError("embedding_failed", "simulated outage")
        if "HOLDEMBED" in joined and _first_time("embed.held"):
            release = Path(os.environ["TEST_OBJECT_DIR"]).parent / "embed.release"
            while not release.exists():
                time.sleep(0.1)
        return super().embed_documents(texts)


class MarkedStore:
    def __init__(self, inner: ObjectStore) -> None:
        self.inner = inner

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        if b"STOREHANGBEFORE" in data and _first_time("store.held"):
            _forever()
        self.inner.put(key, data, content_type=content_type)
        if b"STOREHANGAFTER" in data and _first_time("store.held"):
            _forever()

    def get(self, key: str, *, max_bytes: int) -> bytes:
        return self.inner.get(key, max_bytes=max_bytes)

    def delete(self, key: str) -> None:
        self.inner.delete(key)

    def ensure_ready(self) -> None:
        self.inner.ensure_ready()


def _site_fetcher(settings: Settings, port: int) -> SafeFetcher:
    return SafeFetcher(
        user_agent=settings.crawl_user_agent,
        timeout=settings.fetch_timeout_seconds,
        total_timeout=settings.fetch_total_timeout_seconds,
        max_bytes=settings.fetch_max_bytes,
        max_redirects=settings.fetch_max_redirects,
        allowed_ports=[port],
        resolver=lambda host, p: ["127.0.0.1"] if host == "site.test" else system_resolver(host, p),
        ip_policy=lambda ip: ip == "127.0.0.1" or is_public_ip(ip),
    )


def _install() -> None:
    settings = get_settings()
    built = runtime.build_runtime(settings)
    if os.environ.get("TEST_OBJECT_STORE") == "s3":
        built.store = MarkedStore(S3ObjectStore(settings))
    else:
        built.store = MarkedStore(FileObjectStore(os.environ["TEST_OBJECT_DIR"]))
    built.embedder = MarkedEmbedder(settings.embedding_model)
    if os.environ.get("TEST_PARSER") != "production":
        built.parser = ParserRunner(
            built.parser.limits, command=("-m", "tests.support.hostile_parser", "by-content")
        )
    if port := os.environ.get("TEST_SITE_PORT"):
        built.fetcher = _site_fetcher(settings, int(port))
    runtime.set_runtime(built)


_install()
