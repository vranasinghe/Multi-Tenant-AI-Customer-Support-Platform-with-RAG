"""Celery tasks for ingestion. Thin wrappers: all logic lives in ``app.rag`` and is unit-testable.

Retry policy: transient failures re-queue the job row and ask Celery to retry with exponential
backoff (``ingest_retry_base_seconds``·2ⁿ, capped, with jitter) up to ``ingest_max_attempts``;
permanent failures are recorded on the job/document and never retried automatically.

Admission: a job whose organization is at its limit is not waited for in a worker slot. A new
message is published with a short countdown (at most ``MAX_DEFERRALS`` of them, after which the
periodic sweeper takes over), and finishing a job wakes the organization's next one. Deferral is
not a retry: it consumes no attempt and can never fail a job.

Time limits are set in ``app.workers.celery_app``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from app.core.logging import get_logger
from app.rag import crawl_job, maintenance, pipeline
from app.rag.errors import TransientIngestionError
from app.rag.queue import CeleryJobQueue
from app.rag.runtime import Runtime, get_runtime
from app.workers.celery_app import celery_app

log = get_logger(__name__)

MAX_DEFERRALS = 40
MAX_DEFER_SECONDS = 15.0

_publisher: CeleryJobQueue | None = None


def _retry_delay(task: Any, rt: Runtime) -> int:
    attempt = task.request.retries + 1
    return pipeline.backoff_seconds(
        attempt, rt.settings.ingest_retry_base_seconds, rt.settings.ingest_retry_max_seconds
    )


def _wake(rt: Runtime, org_id: uuid.UUID) -> None:
    global _publisher  # noqa: PLW0603 - one broker connection pool per worker process
    try:
        _publisher = _publisher or CeleryJobQueue(rt.settings)
        maintenance.wake_next(rt, _publisher, org_id)
    except Exception:  # only a shortcut: the deferral messages and the sweeper still run
        log.warning("ingest.wake_failed", exc_info=True)


def _reschedule(task: Any, rt: Runtime, org_id: str, job_id: str, deferrals: int) -> None:
    again = deferrals < MAX_DEFERRALS
    maintenance.defer_job(rt, uuid.UUID(org_id), uuid.UUID(job_id), touch=again)
    if not again:
        return
    countdown = min(MAX_DEFER_SECONDS, rt.settings.ingest_defer_seconds * 2 ** min(deferrals, 10))
    try:
        task.apply_async(
            args=[org_id, job_id],
            kwargs={"deferrals": deferrals + 1},
            countdown=countdown,
            retries=task.request.retries,
        )
    except Exception:  # broker trouble: the job stays queued for the sweeper
        log.warning("queue.publish_failed", job_id=job_id, kind="deferred")


def _execute(
    task: Any,
    runner: Callable[[Runtime, uuid.UUID, uuid.UUID], str],
    org_id: str,
    job_id: str,
    deferrals: int,
) -> str:
    rt = get_runtime()
    org = uuid.UUID(org_id)
    try:
        outcome = runner(rt, org, uuid.UUID(job_id))
    except TransientIngestionError as exc:
        _wake(rt, org)  # the re-queued job released the organization's permit
        raise task.retry(
            exc=exc, countdown=_retry_delay(task, rt), args=[org_id, job_id], kwargs={}
        ) from exc
    if outcome == "deferred":
        _reschedule(task, rt, org_id, job_id, deferrals)
    elif outcome != "skipped":
        _wake(rt, org)
    return outcome


@celery_app.task(name="ingest.process_document", bind=True, max_retries=20, acks_late=True)
def process_document(self: Any, org_id: str, job_id: str, deferrals: int = 0) -> str:
    return _execute(self, pipeline.run_document_job, org_id, job_id, deferrals)


@celery_app.task(name="ingest.crawl_source", bind=True, max_retries=20, acks_late=True)
def crawl_source(self: Any, org_id: str, job_id: str, deferrals: int = 0) -> str:
    return _execute(self, crawl_job.run_crawl_job, org_id, job_id, deferrals)


@celery_app.task(name="ingest.sweep")
def sweep() -> dict[str, int]:
    rt = get_runtime()
    queue = CeleryJobQueue(rt.settings)
    return {
        "requeued": maintenance.sweep_jobs(rt, queue),
        "purged": maintenance.purge_storage(rt),
    }
