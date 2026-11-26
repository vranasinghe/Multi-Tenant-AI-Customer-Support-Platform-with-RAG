"""Periodic maintenance: re-queue stuck jobs and finish pending storage deletions, plus the
bookkeeping for jobs waiting on their organization's admission limit.

Cross-tenant discovery goes through two narrow SECURITY DEFINER functions (no BYPASSRLS role);
each item is then handled inside its own organization's context.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.logging import get_logger
from app.models.identity import utcnow
from app.rag.errors import USER_MESSAGES
from app.rag.pipeline import (
    REFRESH_SOURCE_SQL,
    active_jobs,
    fail_interrupted_pages,
    lock_source,
)
from app.rag.queue import JobQueue
from app.rag.storage import StorageError, key_belongs_to_org

if TYPE_CHECKING:
    import uuid

    from app.rag.runtime import Runtime

log = get_logger(__name__)

_INTERRUPTED = "Processing was interrupted too many times. Retry."


def sweep_jobs(rt: Runtime, queue: JobQueue, *, now_offset: timedelta = timedelta(0)) -> int:
    """Re-publish jobs that are stuck or were never delivered. Returns how many were re-queued.

    * ``processing`` with a stale heartbeat: the worker died; reset to ``queued`` and re-send.
    * ``queued`` for longer than a couple of minutes: the publish was lost; send again.
    A job that reached ``max_attempts`` is failed instead of retried forever.
    """
    now = utcnow() + now_offset
    stuck_before = now - timedelta(seconds=rt.settings.ingest_stuck_after_seconds)
    queued_before = now - timedelta(seconds=120)
    with rt.session_factory() as session, session.begin():
        rows = session.execute(
            text("SELECT job_id, org_id, kind, status FROM app.list_stuck_jobs(:s, :q)"),
            {"s": stuck_before, "q": queued_before},
        ).all()
    requeued = 0
    for job_id, org_id, kind, status in rows:
        with rt.tenant_tx(org_id) as s:
            job = s.execute(
                text("SELECT document_id, source_id FROM ingestion_jobs WHERE id = :id"),
                {"id": job_id},
            ).first()
            if job is None:
                continue
            document_id, source_id = job
            if status == "processing":
                lock_source(s, source_id)
                if document_id is not None:  # same lock order as publication and deletion
                    s.execute(
                        text("SELECT 1 FROM documents WHERE id = :id FOR UPDATE"),
                        {"id": document_id},
                    )
                # Re-checked here: the worker may have heartbeated since the job was listed.
                reset = s.execute(
                    text(
                        "UPDATE ingestion_jobs SET status = CASE WHEN attempt >= max_attempts "
                        "THEN 'failed' ELSE 'queued' END, queued_at = now(), "
                        "error_code = CASE WHEN attempt >= max_attempts THEN 'internal_error' "
                        "ELSE error_code END, finished_at = CASE WHEN attempt >= max_attempts "
                        "THEN now() END WHERE id = :id AND status = 'processing' "
                        "AND coalesce(heartbeat_at, started_at) < :stuck RETURNING id"
                    ),
                    {"id": job_id, "stuck": stuck_before},
                ).first()
                if reset is None:
                    continue
            state = s.scalar(
                text("SELECT status FROM ingestion_jobs WHERE id = :id"), {"id": job_id}
            )
            # Only a job this sweep gave up on: an older one may have a newer job behind it.
            if state == "failed" and status == "processing":
                s.execute(
                    text(
                        "UPDATE documents SET status = 'failed', error_code = 'internal_error', "
                        "error_message = :msg WHERE id = :id AND status IN ('queued', 'processing')"
                    ),
                    {"id": document_id, "msg": _INTERRUPTED},
                )
                if document_id is None:
                    fail_interrupted_pages(
                        s, source_id, "internal_error", USER_MESSAGES["internal_error"]
                    )
                s.execute(REFRESH_SOURCE_SQL, {"sid": source_id})
            elif state == "queued" and status == "processing":
                s.execute(
                    text("UPDATE documents SET status = 'queued' WHERE id = :id"),
                    {"id": document_id},
                )
        if state == "queued":
            queue.enqueue(org_id=org_id, job_id=job_id, kind=kind)
            requeued += 1
    if rows:
        log.info("maintenance.sweep_jobs", found=len(rows), requeued=requeued)
    return requeued


def defer_job(rt: Runtime, org_id: uuid.UUID, job_id: uuid.UUID, *, touch: bool) -> None:
    """Mark a job as waiting for its organization's permit; it uses no attempt.

    ``touch`` refreshes ``queued_at`` while a rescheduled message is outstanding, so the sweeper
    does not add another. Without it the sweeper republishes the job after its usual delay.
    """
    with rt.tenant_tx(org_id) as s:
        s.execute(
            text(
                "UPDATE ingestion_jobs SET stats = stats || jsonb_build_object('deferred', true), "
                "queued_at = CASE WHEN :touch THEN now() ELSE queued_at END "
                "WHERE id = :id AND status = 'queued'"
            ),
            {"id": job_id, "touch": touch},
        )


def wake_next(rt: Runtime, queue: JobQueue, org_id: uuid.UUID) -> bool:
    """Publish the organization's oldest deferred job if a permit is free.

    Duplicate messages are harmless: only one delivery can claim the job. Jobs waiting for a
    retry backoff (they carry an ``error_code``) are left to their own schedule.
    """
    with rt.tenant_tx(org_id) as s:
        if active_jobs(s, rt, org_id) >= rt.settings.ingest_max_active_per_org:
            return False
        row = s.execute(
            text(
                "SELECT id, kind FROM ingestion_jobs WHERE org_id = :org AND status = 'queued' "
                "AND error_code IS NULL AND jsonb_exists(stats, 'deferred') ORDER BY id LIMIT 1"
            ),
            {"org": org_id},
        ).first()
    if row is None:
        return False
    queue.enqueue(org_id=org_id, job_id=row[0], kind=row[1])
    return True


def purge_storage(rt: Runtime, *, limit: int = 100) -> int:
    """Delete originals that are no longer wanted. Returns the number of objects deleted.

    Covers originals of removed or re-published documents and uploads that were never published.
    The latter carry a time before which they are left alone (see ``originals``).
    """
    with rt.session_factory() as session, session.begin():
        rows = session.execute(
            text(
                "SELECT deletion_id, org_id, storage_key "
                "FROM app.list_pending_storage_deletions(:n)"
            ),
            {"n": limit},
        ).all()
    deleted = 0
    for deletion_id, org_id, key in rows:
        # Claim first and commit: a claimed key can no longer be adopted by a publisher, so the
        # object can then be deleted with no transaction open.
        with rt.tenant_tx(org_id) as s:
            claimed = s.execute(
                text(
                    "UPDATE storage_deletions SET attempts = attempts + 1 "
                    "WHERE id = :id AND created_at <= now() "
                    "RETURNING EXISTS (SELECT 1 FROM documents d "
                    "WHERE d.storage_key = storage_deletions.storage_key) AS in_use"
                ),
                {"id": deletion_id},
            ).first()
        if claimed is None:
            continue  # not due yet
        # A key outside the org's prefix, or one a document points at, is never touched.
        if key_belongs_to_org(key, org_id) and not claimed.in_use:
            try:
                rt.store.delete(key)
            except StorageError:
                continue  # the record stays, to be retried
            deleted += 1
        with rt.tenant_tx(org_id) as s:
            s.execute(text("DELETE FROM storage_deletions WHERE id = :id"), {"id": deletion_id})
    return deleted
