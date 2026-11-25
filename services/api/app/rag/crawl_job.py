"""Website crawl job: crawl → store raw HTML → index each page as a document.

A crawl is resumable and idempotent: pages whose content hash and embedding model are unchanged
are skipped, so a retry after a transient failure (or a manual re-sync) only re-embeds what
changed. Pages that disappear are reported (``not_seen``) but not deleted automatically, because
"not reached this time" is not the same as "gone".
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from app.core.ids import new_id
from app.core.logging import get_logger
from app.models.knowledge import Document, KnowledgeSource
from app.rag.crawler import CrawlConfig, CrawledPage, CrawlStats, crawl
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import ExtractedDocument
from app.rag.pipeline import (
    HTML,
    REFRESH_SOURCE_SQL,
    JobClaim,
    claim_job,
    fail_job,
    heartbeat,
    index_document,
    requeue_job,
)
from app.rag.storage import StorageError, document_key

if TYPE_CHECKING:
    from app.rag.runtime import Runtime

log = get_logger(__name__)


def _config_from_source(source: KnowledgeSource, rt: Runtime) -> CrawlConfig:
    cfg = source.config
    s = rt.settings
    return CrawlConfig(
        start_url=str(cfg["start_url"]),
        max_pages=min(int(cfg.get("max_pages", 50)), s.crawl_max_pages_limit),
        max_depth=min(int(cfg.get("max_depth", 2)), s.crawl_max_depth_limit),
        include=tuple(cfg.get("include", [])),
        exclude=tuple(cfg.get("exclude", [])),
        delay_seconds=s.crawl_delay_seconds,
    )


def run_crawl_job(rt: Runtime, org_id: uuid.UUID, job_id: uuid.UUID) -> str:
    claim = claim_job(rt, org_id, job_id)
    if claim is None:
        return "skipped"
    try:
        _run(rt, claim)
    except IngestionError as exc:
        if exc.retryable and claim.attempt < claim.max_attempts:
            requeue_job(rt, claim, exc)
            raise
        fail_job(rt, claim, exc)
        return "failed"
    except StorageError as exc:
        wrapped = TransientIngestionError("storage_error", type(exc).__name__)
        if claim.attempt < claim.max_attempts:
            requeue_job(rt, claim, wrapped)
            raise wrapped from exc
        fail_job(rt, claim, wrapped)
        return "failed"
    except Exception as exc:
        log.exception("crawl.unexpected_error", job_id=str(job_id))
        fail_job(rt, claim, IngestionError("internal_error", type(exc).__name__))
        return "failed"
    return "done"


def _run(rt: Runtime, claim: JobClaim) -> None:
    with rt.tenant_tx(claim.org_id) as s:
        source = s.get(KnowledgeSource, claim.source_id)
        if source is None:
            return
        config = _config_from_source(source, rt)
        known = {
            row[0]
            for row in s.execute(
                select(Document.content_hash).where(
                    Document.chatbot_id == claim.chatbot_id,
                    Document.status == "ready",
                    Document.source_id != claim.source_id,
                    Document.content_hash.is_not(None),
                )
            )
        }
        existing = {
            d.uri: (d.id, d.content_hash, d.status, d.embedding_model)
            for d in s.execute(select(Document).where(Document.source_id == claim.source_id))
            .scalars()
            .all()
        }
        doc_count = s.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.chatbot_id == claim.chatbot_id)
        )

    stats = CrawlStats()
    unchanged = 0
    seen_uris: set[str] = set()
    max_docs = rt.settings.max_documents_per_chatbot
    heartbeat(rt, claim, "crawl")

    for page in crawl(rt.fetcher, config, stats, known_hashes={h for h in known if h is not None}):
        seen_uris.add(page.url)
        prior = existing.get(page.url)
        if (
            prior
            and prior[2] == "ready"
            and prior[1] == page.content_hash
            and prior[3] == rt.embedder.model_id
        ):
            unchanged += 1
            continue
        if prior is None and (doc_count or 0) >= max_docs:
            stats.stopped_at_limit = True
            break
        document_id = _upsert_page(rt, claim, page, prior)
        if prior is None:
            doc_count = (doc_count or 0) + 1
        try:
            index_document(
                rt,
                org_id=claim.org_id,
                chatbot_id=claim.chatbot_id,
                document_id=document_id,
                extracted=ExtractedDocument(blocks=page.blocks, title=page.title),
                title=page.title,
            )
        except IngestionError as exc:
            if exc.retryable:
                raise
            _mark_page_failed(rt, claim, document_id, exc)
            stats.errors += 1
        heartbeat(rt, claim, "crawl", pages=stats.indexed, fetched=stats.fetched)

    not_seen = sorted(set(existing) - seen_uris)
    summary = {**stats.as_dict(), "unchanged": unchanged, "not_seen": len(not_seen)}
    with rt.tenant_tx(claim.org_id) as s:
        s.execute(
            text(
                "UPDATE ingestion_jobs SET status = 'succeeded', finished_at = now(), "
                "stage = 'done', heartbeat_at = now(), stats = stats || CAST(:stats AS jsonb) "
                "WHERE id = :id"
            ),
            {"id": claim.job_id, "stats": _dumps(summary)},
        )
        s.execute(
            text("UPDATE knowledge_sources SET last_synced_at = now() WHERE id = :sid"),
            {"sid": claim.source_id},
        )
        s.execute(REFRESH_SOURCE_SQL, {"sid": claim.source_id})
    log.info("crawl.finished", job_id=str(claim.job_id), indexed=stats.indexed, errors=stats.errors)


def _dumps(value: object) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value)


def _upsert_page(
    rt: Runtime,
    claim: JobClaim,
    page: CrawledPage,
    prior: tuple[uuid.UUID, bytes | None, str, str | None] | None,
) -> uuid.UUID:
    """Create or reset the document for ``page`` and store its raw HTML privately."""
    document_id = prior[0] if prior else new_id()
    key = document_key(claim.org_id, claim.chatbot_id, document_id, 0)
    rt.store.put(key, page.raw_html, content_type="text/html")
    with rt.tenant_tx(claim.org_id) as s:
        if prior is None:
            s.add(
                Document(
                    id=document_id,
                    org_id=claim.org_id,
                    chatbot_id=claim.chatbot_id,
                    source_id=claim.source_id,
                    title=(page.title or page.url)[:300],
                    uri=page.url,
                    storage_key=key,
                    mime_type=HTML,
                    size_bytes=len(page.raw_html),
                    http_etag=page.etag,
                    status="processing",
                )
            )
        else:
            document = s.get(Document, document_id)
            if document is not None:
                document.storage_key = key
                document.size_bytes = len(page.raw_html)
                document.http_etag = page.etag
                document.status = "processing"
    return document_id


def _mark_page_failed(
    rt: Runtime, claim: JobClaim, document_id: uuid.UUID, exc: IngestionError
) -> None:
    with rt.tenant_tx(claim.org_id) as s:
        s.execute(
            text(
                "UPDATE documents SET status = 'failed', error_code = :code, error_message = :msg "
                "WHERE id = :id"
            ),
            {"id": document_id, "code": exc.code, "msg": exc.user_message},
        )
