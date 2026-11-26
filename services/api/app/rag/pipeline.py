"""Ingestion pipeline: claim → read original → extract → dedupe → chunk → embed → persist.

Reliability rules:

* **No duplicate processing.** A job is claimed with a compare-and-set (``queued`` →
  ``processing``);
  a second delivery of the same message claims nothing and exits. A partial unique index also
  forbids two active jobs for one document.
* **Attempt fencing.** ``attempt`` only ever grows, on claim. Every later transition (heartbeat,
  publish, fail, requeue) requires ``status = 'processing' AND attempt = <mine>``, so a worker
  that was reset by the sweeper, superseded or whose document was deleted changes nothing.
* **Per-organization admission.** At most ``ingest_max_active_per_org`` heavy jobs of one
  organization run at once, counted from the job rows themselves; there is no separate permit to
  leak, and a dead worker's row stops counting after the stuck threshold.
* **Isolated parsing.** Originals are parsed in a supervised child (``parser_runner``).
* **Originals are never overwritten.** A re-fetched original gets a new key, published together
  with its chunks (``originals``); a job never publishes from an original that was replaced.
* **Atomic publish.** Chunks are written in one transaction together with the document's new
  ``version``, ``ready`` status and the job's ``succeeded`` state, and older versions' chunks are
  deleted in the same transaction. Readers never see half-indexed or duplicated content, and a
  crash or retry before commit leaves the previous version fully intact.
* **Safe retries.** Permanent problems (corrupt file, no text) fail fast with a stable code.
  Transient ones (embedding provider, storage, DB hiccup) put the job back to ``queued`` and let
  Celery retry with exponential backoff until ``max_attempts``.
* **No sensitive logging.** Logs carry ids, stages, counts and error codes, never document text.
"""

from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, insert, select, text
from sqlalchemy.exc import DBAPIError, OperationalError

from app.core.ids import new_id
from app.core.logging import get_logger
from app.models.knowledge import Document, DocumentChunk, KnowledgeSource
from app.rag import originals
from app.rag.chunking import chunk_blocks
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import ExtractedDocument
from app.rag.parser_runner import ParseCancelledError
from app.rag.storage import ObjectNotFoundError, StorageError, key_belongs_to_org

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from app.rag.runtime import Runtime

log = get_logger(__name__)

HTML = "text/html"

REFRESH_SOURCE_SQL = text(
    """
    UPDATE knowledge_sources s SET
      stats = jsonb_build_object(
        'documents', x.total, 'ready', x.ready, 'failed', x.failed,
        'processing', x.processing, 'chunks', x.chunks, 'bytes', x.bytes),
      status = CASE
        WHEN EXISTS (SELECT 1 FROM ingestion_jobs j
                     WHERE j.source_id = s.id AND j.status IN ('queued', 'processing'))
          THEN 'syncing'
        WHEN x.total = 0 AND (
          SELECT j.status FROM ingestion_jobs j WHERE j.source_id = s.id
          ORDER BY j.queued_at DESC, j.id DESC LIMIT 1) = 'failed' THEN 'failed'
        WHEN x.total = 0 THEN 'pending'
        WHEN x.failed = 0 THEN 'ready'
        WHEN x.ready = 0 THEN 'failed'
        ELSE 'partial' END
    FROM (
      SELECT count(*) AS total,
             count(*) FILTER (WHERE status = 'ready') AS ready,
             count(*) FILTER (WHERE status = 'failed') AS failed,
             count(*) FILTER (WHERE status IN ('queued', 'processing')) AS processing,
             coalesce(sum(chunk_count), 0) AS chunks,
             coalesce(sum(size_bytes), 0) AS bytes
      FROM documents WHERE source_id = :sid
    ) x
    WHERE s.id = :sid
    """
)


@dataclass(frozen=True)
class JobClaim:
    job_id: uuid.UUID
    org_id: uuid.UUID
    chatbot_id: uuid.UUID
    source_id: uuid.UUID
    document_id: uuid.UUID | None
    kind: str
    attempt: int
    max_attempts: int


def backoff_seconds(attempt: int, base: int, cap: int) -> int:
    """Exponential backoff with ±20% jitter: base·2^(attempt-1), capped."""
    raw = min(cap, base * (2 ** max(0, attempt - 1)))
    return int(raw * random.uniform(0.8, 1.2)) if raw else 0  # jitter, not security  # noqa: S311


# ---------------------------------------------------------------------------- job state


class JobDeferredError(Exception):
    """The organization already runs its permitted heavy ingestion work."""


class StaleClaimError(Exception):
    """This attempt no longer owns the job (deleted, reset or superseded)."""


def _owner(claim: JobClaim) -> dict[str, Any]:
    return {"id": claim.job_id, "attempt": claim.attempt}


def active_jobs(s: Session, rt: Runtime, org_id: uuid.UUID) -> int:
    """Heavy jobs of ``org_id`` that are running and have not gone silent."""
    return int(
        s.execute(
            text(
                "SELECT count(*) FROM ingestion_jobs WHERE org_id = :org "
                "AND status = 'processing' "
                "AND coalesce(heartbeat_at, started_at) > now() - make_interval(secs => :stuck)"
            ),
            {"org": org_id, "stuck": rt.settings.ingest_stuck_after_seconds},
        ).scalar_one()
    )


def claim_job(rt: Runtime, org_id: uuid.UUID, job_id: uuid.UUID) -> JobClaim | None:
    """Atomically move a ``queued`` job to ``processing``; ``None`` if someone else has it.

    Raises ``JobDeferredError``, leaving the job untouched, when the organization is at its limit.
    """
    with rt.tenant_tx(org_id) as s:
        # Serializes admission for this organization across every worker process.
        s.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"ingest-admission:{org_id}"},
        )
        state = s.execute(
            text("SELECT status FROM ingestion_jobs WHERE id = :id AND org_id = :org"),
            {"id": job_id, "org": org_id},
        ).scalar_one_or_none()
        if state != "queued":
            return None
        if active_jobs(s, rt, org_id) >= rt.settings.ingest_max_active_per_org:
            raise JobDeferredError
        row = s.execute(
            text(
                """
                UPDATE ingestion_jobs
                SET status = 'processing', attempt = attempt + 1,
                    started_at = coalesce(started_at, now()), heartbeat_at = now(),
                    stage = 'validate', error_code = NULL, error_detail = NULL
                WHERE id = :id AND org_id = :org AND status = 'queued'
                RETURNING chatbot_id, source_id, document_id, kind, attempt, max_attempts
                """
            ),
            {"id": job_id, "org": org_id},
        ).first()
    if row is None:
        return None
    return JobClaim(job_id, org_id, *row)


def lock_source(s: Session, source_id: uuid.UUID) -> None:
    """Take first, before document and job: deleting a source locks in that order too."""
    s.execute(
        text("SELECT 1 FROM knowledge_sources WHERE id = :id FOR KEY SHARE"), {"id": source_id}
    )


def lock_claim(s: Session, claim: JobClaim) -> bool:
    """Lock the job row if this attempt still owns it. Lock source and document first."""
    return (
        s.execute(
            text(
                "SELECT 1 FROM ingestion_jobs "
                "WHERE id = :id AND status = 'processing' AND attempt = :attempt FOR UPDATE"
            ),
            _owner(claim),
        ).first()
        is not None
    )


def _lock_document(s: Session, document_id: uuid.UUID | None) -> None:
    if document_id is not None:
        s.execute(text("SELECT 1 FROM documents WHERE id = :id FOR UPDATE"), {"id": document_id})


def claim_is_current(rt: Runtime, claim: JobClaim) -> bool:
    """Refresh the heartbeat if this attempt still owns the job."""
    with rt.tenant_tx(claim.org_id) as s:
        return (
            s.execute(
                text(
                    "UPDATE ingestion_jobs SET heartbeat_at = now() WHERE id = :id "
                    "AND status = 'processing' AND attempt = :attempt RETURNING id"
                ),
                _owner(claim),
            ).first()
            is not None
        )


def heartbeat(rt: Runtime, claim: JobClaim, stage: str, **stats: Any) -> None:
    with rt.tenant_tx(claim.org_id) as s:
        owned = s.execute(
            text(
                "UPDATE ingestion_jobs SET heartbeat_at = now(), stage = :stage, "
                "stats = stats || CAST(:stats AS jsonb) WHERE id = :id "
                "AND status = 'processing' AND attempt = :attempt RETURNING id"
            ),
            {**_owner(claim), "stage": stage, "stats": _json(stats)},
        ).first()
    if owned is None:
        raise StaleClaimError


def _json(value: dict[str, Any]) -> str:
    import json  # noqa: PLC0415

    return json.dumps(value)


def fail_interrupted_pages(s: Session, source_id: uuid.UUID, code: str, message: str) -> None:
    """A crawl that ends for good must not leave pages it was indexing as ``processing``."""
    s.execute(
        text(
            "UPDATE documents d SET status = 'failed', error_code = :code, error_message = :msg "
            "WHERE d.source_id = :sid AND d.status = 'processing' AND NOT EXISTS ("
            "SELECT 1 FROM ingestion_jobs j WHERE j.document_id = d.id "
            "AND j.status IN ('queued', 'processing'))"
        ),
        {"sid": source_id, "code": code, "msg": message},
    )


def fail_job(rt: Runtime, claim: JobClaim, exc: IngestionError) -> bool:
    """Record a final failure. ``False``, changing nothing, if the claim was lost."""
    with rt.tenant_tx(claim.org_id) as s:
        lock_source(s, claim.source_id)
        _lock_document(s, claim.document_id)
        owned = s.execute(
            text(
                "UPDATE ingestion_jobs SET status = 'failed', finished_at = now(), "
                "error_code = :code, error_detail = :detail WHERE id = :id "
                "AND status = 'processing' AND attempt = :attempt RETURNING id"
            ),
            {**_owner(claim), "code": exc.code, "detail": (exc.detail or "")[:300]},
        ).first()
        if owned is None:
            return False
        if claim.document_id is not None:
            s.execute(
                text(
                    "UPDATE documents SET status = 'failed', error_code = :code, "
                    "error_message = :msg WHERE id = :id"
                ),
                {"id": claim.document_id, "code": exc.code, "msg": exc.user_message},
            )
        else:
            fail_interrupted_pages(s, claim.source_id, exc.code, exc.user_message)
        s.execute(REFRESH_SOURCE_SQL, {"sid": claim.source_id})
    log.warning("ingest.job_failed", job_id=str(claim.job_id), code=exc.code, attempt=claim.attempt)
    return True


def requeue_job(rt: Runtime, claim: JobClaim, exc: IngestionError) -> bool:
    """Back to ``queued`` so the next delivery can claim it (attempt count is kept).

    ``False``, changing nothing, if the claim was lost.
    """
    with rt.tenant_tx(claim.org_id) as s:
        _lock_document(s, claim.document_id)
        owned = s.execute(
            text(
                "UPDATE ingestion_jobs SET status = 'queued', queued_at = now(), "
                "error_code = :code WHERE id = :id "
                "AND status = 'processing' AND attempt = :attempt RETURNING id"
            ),
            {**_owner(claim), "code": exc.code},
        ).first()
        if owned is None:
            return False
        if claim.document_id is not None:
            s.execute(
                text("UPDATE documents SET status = 'queued' WHERE id = :id"),
                {"id": claim.document_id},
            )
    return True


def _abandoned(rt: Runtime, claim: JobClaim) -> str:
    """Outcome for an attempt that lost its claim: ``gone`` if deleted, else ``stale``."""
    with rt.tenant_tx(claim.org_id) as s:
        if claim.document_id is not None:
            exists = s.get(Document, claim.document_id) is not None
        else:
            exists = s.get(KnowledgeSource, claim.source_id) is not None
    outcome = "stale" if exists else "gone"
    log.info("ingest.attempt_abandoned", job_id=str(claim.job_id), outcome=outcome)
    return outcome


def run_claimed(
    rt: Runtime,
    claim: JobClaim,
    work: Callable[[], str],
    *,
    transient: tuple[type[Exception], ...],
    transient_code: str,
) -> str:
    """Run ``work`` for a claimed job and record its outcome, only while the claim holds.

    Raises ``TransientIngestionError`` (after re-queueing the job) when Celery should retry.
    """
    failure: IngestionError
    try:
        return work()
    except (StaleClaimError, ParseCancelledError):
        return _abandoned(rt, claim)
    except IngestionError as exc:
        failure = exc
    except SoftTimeLimitExceeded:
        failure = TransientIngestionError("task_timeout", "task soft time limit")
    except transient as exc:
        failure = TransientIngestionError(transient_code, type(exc).__name__)
    except Exception as exc:  # unexpected bug: record it, don't loop forever
        log.exception("ingest.unexpected_error", job_id=str(claim.job_id))
        failure = IngestionError("internal_error", type(exc).__name__)
    if failure.retryable and claim.attempt < claim.max_attempts:
        if requeue_job(rt, claim, failure):
            raise failure
    elif fail_job(rt, claim, failure):
        return "failed"
    return _abandoned(rt, claim)


# ---------------------------------------------------------------------------- extraction


def extract_stored(
    rt: Runtime,
    data: bytes,
    mime_type: str,
    uri: str,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> ExtractedDocument:
    """Parse a stored original in the supervised child, never in this process."""
    if mime_type == HTML:
        page = rt.parser.html(data, uri, cancelled=cancelled)
        doc = ExtractedDocument(blocks=page.blocks, title=page.title)
        if not doc.text.strip():
            raise IngestionError("no_text")
        return doc
    return rt.parser.document(data, mime_type, rt.limits, cancelled=cancelled)


# --------------------------------------------------------------------------- indexing


@dataclass(frozen=True)
class IndexResult:
    chunks: int
    tokens: int
    version: int


@dataclass(frozen=True)
class StoredOriginal:
    """An object written for a document that does not point at it yet."""

    key: str
    size: int
    etag: str | None


def index_document(
    rt: Runtime,
    *,
    org_id: uuid.UUID,
    chatbot_id: uuid.UUID,
    document_id: uuid.UUID,
    extracted: ExtractedDocument,
    claim: JobClaim,
    title: str | None = None,
    completes_job: bool = False,
    on_stage: Callable[[str], None] | None = None,
    original: StoredOriginal | None = None,
    read_from: str | None = None,
) -> IndexResult | None:
    """Chunk, embed and atomically publish ``extracted``. ``None`` if the document was deleted.

    ``original`` is adopted in the publishing transaction. ``read_from`` is the key
    ``extracted`` came from: publishing is refused if the document has moved to another one.

    Raises ``StaleClaimError``, publishing nothing, if ``claim`` was lost before the commit.
    """
    stage = on_stage or (lambda _name: None)
    digest = hashlib.sha256(extracted.text.encode()).digest()

    stage("dedupe")
    with rt.tenant_tx(org_id) as s:
        duplicate = s.scalar(
            select(Document.id).where(
                Document.chatbot_id == chatbot_id,
                Document.content_hash == digest,
                Document.status == "ready",
                Document.id != document_id,
            )
        )
    if duplicate is not None:
        raise IngestionError("duplicate_content")

    stage("chunk")
    chunks = chunk_blocks(extracted.blocks, rt.chunking, title=title or extracted.title)
    if not chunks:
        raise IngestionError("no_text")

    stage("embed")
    texts = [c.embedded_text or c.content for c in chunks]
    vectors: list[list[float]] = []
    batch = rt.settings.embedding_batch_size
    for start in range(0, len(texts), batch):
        stage("embed")
        vectors.extend(rt.embedder.embed_documents(texts[start : start + batch]))
    if len(vectors) != len(chunks):
        raise IngestionError("embedding_failed", "embedding count mismatch")

    stage("persist")
    model = rt.embedder.model_id
    meta = {
        "chunker": "v1",
        "size_tokens": rt.chunking.size_tokens,
        "overlap_tokens": rt.chunking.overlap_tokens,
    }
    with rt.tenant_tx(org_id) as s:
        lock_source(s, claim.source_id)
        document = s.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        ).scalar_one_or_none()
        if document is None:
            return None  # deleted while processing: its job and chunks are already gone
        if not lock_claim(s, claim):
            raise StaleClaimError
        _settle_original(s, document, original, read_from)
        version = document.version + 1
        s.execute(
            insert(DocumentChunk),
            [
                {
                    "id": new_id(),
                    "org_id": org_id,
                    "chatbot_id": chatbot_id,
                    "document_id": document_id,
                    "document_version": version,
                    "ordinal": chunk.ordinal,
                    "content": chunk.content,
                    "embedded_text": chunk.embedded_text,
                    "token_count": chunk.token_count,
                    "heading_path": list(chunk.heading_path),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "embedding": vector,
                    "embedding_model": model,
                    "meta": meta,
                }
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
        )
        s.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id, DocumentChunk.document_version < version
            )
        )
        tokens = sum(c.token_count for c in chunks)
        document.version = version
        document.status = "ready"
        document.content_hash = digest
        document.chunk_count = len(chunks)
        document.token_count = tokens
        document.page_count = extracted.page_count
        document.embedding_model = model
        document.error_code = None
        document.error_message = None
        if title:
            document.title = title[:300]
        if completes_job:
            s.execute(
                text(
                    "UPDATE ingestion_jobs SET status = 'succeeded', finished_at = now(), "
                    "stage = 'done', heartbeat_at = now(), error_code = NULL, "
                    "stats = stats || CAST(:stats AS jsonb) WHERE id = :id"
                ),
                {"id": claim.job_id, "stats": _json({"chunks": len(chunks), "tokens": tokens})},
            )
        s.execute(REFRESH_SOURCE_SQL, {"sid": document.source_id})
    log.info("ingest.document_indexed", document_id=str(document_id), chunks=len(chunks))
    return IndexResult(len(chunks), tokens, version)


def _settle_original(
    s: Session, document: Document, original: StoredOriginal | None, read_from: str | None
) -> None:
    """In the publishing transaction: the chunks and the original they came from agree."""
    if read_from is not None and document.storage_key != read_from:
        raise TransientIngestionError("storage_error", "original was replaced")
    if original is not None:
        originals.adopt(s, document, original.key, size=original.size, etag=original.etag)


# ------------------------------------------------------------------- document job runner


def run_document_job(rt: Runtime, org_id: uuid.UUID, job_id: uuid.UUID) -> str:
    """Process one ``process_document`` job.

    Returns ``done|skipped|deferred|failed|gone|stale``. Raises ``TransientIngestionError``
    (after re-queueing the job) when Celery should retry.
    """
    try:
        claim = claim_job(rt, org_id, job_id)
    except JobDeferredError:
        log.info("ingest.job_deferred", job_id=str(job_id))
        return "deferred"
    if claim is None or claim.document_id is None:
        log.info("ingest.job_skipped", job_id=str(job_id))
        return "skipped"
    return run_claimed(
        rt,
        claim,
        lambda: _process_document(rt, claim),
        transient=(OperationalError, DBAPIError, StorageError),
        transient_code="internal_error",
    )


def _process_document(rt: Runtime, claim: JobClaim) -> str:
    assert claim.document_id is not None  # noqa: S101
    document_id = claim.document_id
    with rt.tenant_tx(claim.org_id) as s:
        document = s.get(Document, document_id, with_for_update=True)
        if document is None:
            return "gone"
        if not lock_claim(s, claim):
            raise StaleClaimError
        document.status = "processing"
        document.error_code = None
        document.error_message = None
        storage_key = document.storage_key
        mime_type = document.mime_type or ""
        file_hash = document.file_hash
        uri = document.uri
        is_web = mime_type == HTML
    if not storage_key or not key_belongs_to_org(storage_key, claim.org_id):
        raise IngestionError("storage_error", "missing or foreign storage key")

    heartbeat(rt, claim, "extract")
    try:
        data = rt.store.get(storage_key, max_bytes=rt.settings.upload_max_bytes + 1024)
    except ObjectNotFoundError as exc:
        if _current_key(rt, claim.org_id, document_id) != storage_key:
            raise TransientIngestionError("storage_error", "original was replaced") from exc
        raise IngestionError("storage_error", "original is missing") from exc
    except StorageError as exc:
        raise TransientIngestionError("storage_error", "storage unavailable") from exc
    if file_hash is not None and hashlib.sha256(data).digest() != file_hash:
        raise IngestionError("corrupt", "stored file does not match its recorded hash")

    extracted = extract_stored(
        rt, data, mime_type, uri, cancelled=lambda: not claim_is_current(rt, claim)
    )
    result = index_document(
        rt,
        org_id=claim.org_id,
        chatbot_id=claim.chatbot_id,
        document_id=document_id,
        extracted=extracted,
        claim=claim,
        title=extracted.title if is_web else None,
        completes_job=True,
        on_stage=lambda name: heartbeat(rt, claim, name),
        read_from=storage_key,
    )
    return "done" if result is not None else "gone"


def _current_key(rt: Runtime, org_id: uuid.UUID, document_id: uuid.UUID) -> str | None:
    with rt.tenant_tx(org_id) as s:
        return s.scalar(select(Document.storage_key).where(Document.id == document_id))
