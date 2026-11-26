"""Website crawl job: crawl → store raw HTML → index each page as a document.

A crawl is resumable and idempotent: pages whose content hash and embedding model are unchanged
are skipped, so a retry after a transient failure (or a manual re-sync) only re-embeds what
changed. Pages that disappear are reported (``not_seen``) but not deleted automatically, because
"not reached this time" is not the same as "gone".

Every write is fenced by the job's attempt (see ``pipeline``): a superseded, reset or deleted
crawl stops without publishing. Pages are parsed in the supervised parser child.

A page's raw HTML is stored under a new key each time and becomes the document's original only
when this attempt publishes it (see ``originals``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from app.core.ids import new_id
from app.core.logging import get_logger
from app.models.knowledge import Document, KnowledgeSource
from app.rag import originals
from app.rag.crawler import CrawlConfig, CrawledPage, CrawlStats, crawl
from app.rag.errors import IngestionError
from app.rag.extract import ExtractedDocument
from app.rag.html_extract import HtmlPage
from app.rag.pipeline import (
    HTML,
    REFRESH_SOURCE_SQL,
    JobClaim,
    JobDeferredError,
    StaleClaimError,
    StoredOriginal,
    claim_is_current,
    claim_job,
    heartbeat,
    index_document,
    lock_claim,
    lock_source,
    run_claimed,
)
from app.rag.storage import StorageError, generation_key

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
    """Returns ``done|skipped|deferred|failed|gone|stale``; see ``run_document_job``."""
    try:
        claim = claim_job(rt, org_id, job_id)
    except JobDeferredError:
        log.info("crawl.job_deferred", job_id=str(job_id))
        return "deferred"
    if claim is None:
        return "skipped"

    def work() -> str:
        _run(rt, claim)
        return "done"

    return run_claimed(rt, claim, work, transient=(StorageError,), transient_code="storage_error")


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

    def current() -> bool:
        return claim_is_current(rt, claim)

    def parse(body: bytes, charset: str, url: str) -> HtmlPage:
        return rt.parser.html(body, url, charset, cancelled=lambda: not current())

    for page in crawl(
        rt.fetcher,
        config,
        stats,
        known_hashes={h for h in known if h is not None},
        should_continue=current,
        parse=parse,
    ):
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
        if prior is None:
            doc_count = (doc_count or 0) + 1
        if not _publish_page(rt, claim, page, prior[0] if prior else None):
            stats.errors += 1
        heartbeat(rt, claim, "crawl", pages=stats.indexed, fetched=stats.fetched)

    not_seen = sorted(set(existing) - seen_uris)
    summary = {**stats.as_dict(), "unchanged": unchanged, "not_seen": len(not_seen)}
    with rt.tenant_tx(claim.org_id) as s:
        if not lock_claim(s, claim):
            raise StaleClaimError
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


def _publish_page(
    rt: Runtime, claim: JobClaim, page: CrawledPage, known_id: uuid.UUID | None
) -> bool:
    """Store, record and index one page. ``False`` if it was recorded as failed."""
    document_id = known_id or new_id()
    key = generation_key(claim.org_id, claim.chatbot_id, document_id, new_id())
    heartbeat(rt, claim, "crawl")
    with rt.tenant_tx(claim.org_id) as s:  # on record before the object can exist
        lock_source(s, claim.source_id)
        if not lock_claim(s, claim):
            raise StaleClaimError
        originals.stage(s, claim.org_id, key, grace_seconds=originals.grace_seconds(rt.settings))
    rt.store.put(key, page.raw_html, content_type="text/html")  # no transaction open
    try:
        pending = _record_page(rt, claim, page, document_id, key, new=known_id is None)
        try:
            index_document(
                rt,
                org_id=claim.org_id,
                chatbot_id=claim.chatbot_id,
                document_id=document_id,
                extracted=ExtractedDocument(blocks=page.blocks, title=page.title),
                claim=claim,
                title=page.title,
                original=pending,
                on_stage=lambda _name: heartbeat(rt, claim, "crawl"),
            )
        except IngestionError as exc:
            if exc.retryable:
                raise
            _mark_page_failed(rt, claim, document_id, exc)
            return False
        return True
    finally:
        # The upload has returned, so whatever was not adopted can be reclaimed straight away.
        originals.release(rt, claim.org_id, key)


def _record_page(
    rt: Runtime,
    claim: JobClaim,
    page: CrawledPage,
    document_id: uuid.UUID,
    key: str,
    *,
    new: bool,
) -> StoredOriginal | None:
    """Create or reset the page's document. Returns the original still waiting to be published.

    A document that has published a version keeps that version's original until the next version
    commits. One that never has takes the new original now, so that it can be reprocessed.
    """
    stored = StoredOriginal(key, len(page.raw_html), page.etag)
    with rt.tenant_tx(claim.org_id) as s:
        lock_source(s, claim.source_id)
        document = None if new else s.get(Document, document_id, with_for_update=True)
        if not lock_claim(s, claim):
            raise StaleClaimError
        if new:
            document = Document(
                id=document_id,
                org_id=claim.org_id,
                chatbot_id=claim.chatbot_id,
                source_id=claim.source_id,
                title=(page.title or page.url)[:300],
                uri=page.url,
                storage_key=key,
                mime_type=HTML,
            )
            s.add(document)
        if document is None:
            return None  # deleted since the crawl started
        document.status = "processing"
        if document.version:
            return stored
        originals.adopt(s, document, key, size=stored.size, etag=stored.etag)
    return None


def _mark_page_failed(
    rt: Runtime, claim: JobClaim, document_id: uuid.UUID, exc: IngestionError
) -> None:
    with rt.tenant_tx(claim.org_id) as s:
        lock_source(s, claim.source_id)
        s.execute(text("SELECT 1 FROM documents WHERE id = :id FOR UPDATE"), {"id": document_id})
        if not lock_claim(s, claim):
            raise StaleClaimError
        s.execute(
            text(
                "UPDATE documents SET status = 'failed', error_code = :code, error_message = :msg "
                "WHERE id = :id"
            ),
            {"id": document_id, "code": exc.code, "msg": exc.user_message},
        )
