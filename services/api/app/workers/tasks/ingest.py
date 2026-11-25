"""Celery tasks for ingestion. Thin wrappers: all logic lives in ``app.rag`` and is unit-testable.

Retry policy: transient failures re-queue the job row and ask Celery to retry with exponential
backoff (``ingest_retry_base_seconds``·2ⁿ, capped, with jitter) up to ``ingest_max_attempts``;
permanent failures are recorded on the job/document and never retried automatically.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.logging import get_logger
from app.rag import crawl_job, maintenance, pipeline
from app.rag.errors import TransientIngestionError
from app.rag.queue import CeleryJobQueue
from app.rag.runtime import get_runtime
from app.workers.celery_app import celery_app

log = get_logger(__name__)


def _retry_delay(task: Any, exc: TransientIngestionError) -> int:
    rt = get_runtime()
    attempt = task.request.retries + 1
    return pipeline.backoff_seconds(
        attempt, rt.settings.ingest_retry_base_seconds, rt.settings.ingest_retry_max_seconds
    )


@celery_app.task(name="ingest.process_document", bind=True, max_retries=20, acks_late=True)
def process_document(self: Any, org_id: str, job_id: str) -> str:
    rt = get_runtime()
    try:
        return pipeline.run_document_job(rt, uuid.UUID(org_id), uuid.UUID(job_id))
    except TransientIngestionError as exc:
        raise self.retry(exc=exc, countdown=_retry_delay(self, exc)) from exc


@celery_app.task(name="ingest.crawl_source", bind=True, max_retries=20, acks_late=True)
def crawl_source(self: Any, org_id: str, job_id: str) -> str:
    rt = get_runtime()
    try:
        return crawl_job.run_crawl_job(rt, uuid.UUID(org_id), uuid.UUID(job_id))
    except TransientIngestionError as exc:
        raise self.retry(exc=exc, countdown=_retry_delay(self, exc)) from exc


@celery_app.task(name="ingest.sweep")
def sweep() -> dict[str, int]:
    rt = get_runtime()
    queue = CeleryJobQueue(rt.settings)
    return {
        "requeued": maintenance.sweep_jobs(rt, queue),
        "purged": maintenance.purge_storage(rt),
    }
