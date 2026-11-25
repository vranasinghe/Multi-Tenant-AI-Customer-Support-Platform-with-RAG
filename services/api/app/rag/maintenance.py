"""Periodic maintenance: re-queue stuck jobs and finish pending storage deletions.

Cross-tenant discovery goes through two narrow SECURITY DEFINER functions (no BYPASSRLS role);
each item is then handled inside its own organization's context.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.core.logging import get_logger
from app.models.identity import utcnow
from app.rag.queue import JobQueue
from app.rag.storage import StorageError, key_belongs_to_org

if TYPE_CHECKING:
    from app.rag.runtime import Runtime

log = get_logger(__name__)


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
            if status == "processing":
                s.execute(
                    text(
                        "UPDATE ingestion_jobs SET status = CASE WHEN attempt >= max_attempts "
                        "THEN 'failed' ELSE 'queued' END, queued_at = now(), "
                        "error_code = CASE WHEN attempt >= max_attempts THEN 'internal_error' "
                        "ELSE error_code END, finished_at = CASE WHEN attempt >= max_attempts "
                        "THEN now() END WHERE id = :id AND status = 'processing'"
                    ),
                    {"id": job_id},
                )
            state = s.scalar(
                text("SELECT status FROM ingestion_jobs WHERE id = :id"), {"id": job_id}
            )
            if state == "failed":
                s.execute(
                    text(
                        "UPDATE documents SET status = 'failed', error_code = 'internal_error', "
                        "error_message = 'Processing was interrupted too many times. Retry.' "
                        "WHERE id = (SELECT document_id FROM ingestion_jobs WHERE id = :id) "
                        "AND status IN ('queued', 'processing')"
                    ),
                    {"id": job_id},
                )
        if state == "queued":
            queue.enqueue(org_id=org_id, job_id=job_id, kind=kind)
            requeued += 1
    if rows:
        log.info("maintenance.sweep_jobs", found=len(rows), requeued=requeued)
    return requeued


def purge_storage(rt: Runtime, *, limit: int = 100) -> int:
    """Delete originals whose documents were removed. Returns the number of objects deleted."""
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
        if key_belongs_to_org(key, org_id):  # a key outside the org's prefix is never touched
            try:
                rt.store.delete(key)
            except StorageError:
                with rt.tenant_tx(org_id) as s:
                    s.execute(
                        text("UPDATE storage_deletions SET attempts = attempts + 1 WHERE id = :id"),
                        {"id": deletion_id},
                    )
                continue
            deleted += 1
        with rt.tenant_tx(org_id) as s:
            s.execute(text("DELETE FROM storage_deletions WHERE id = :id"), {"id": deletion_id})
    return deleted
