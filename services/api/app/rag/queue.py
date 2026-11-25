"""Job publishing. Postgres is the source of truth; the broker only carries ``(org_id, job_id)``.

Messages contain ids, never document text, URLs or tokens. If publishing fails after the job row
was committed, the job stays ``queued`` and the maintenance sweeper re-publishes it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Protocol

from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.core.config import Settings

log = get_logger(__name__)

TASK_BY_KIND = {
    "process_document": ("ingest.process_document", "ingest"),
    "crawl": ("ingest.crawl_source", "crawl"),
}


class JobQueue(Protocol):
    def enqueue(self, *, org_id: uuid.UUID, job_id: uuid.UUID, kind: str) -> None: ...


class CeleryJobQueue:
    def __init__(self, settings: Settings) -> None:
        from app.workers.celery_app import create_celery_app  # noqa: PLC0415

        self._celery = create_celery_app(settings)

    def enqueue(self, *, org_id: uuid.UUID, job_id: uuid.UUID, kind: str) -> None:
        name, queue = TASK_BY_KIND[kind]
        try:
            self._celery.send_task(name, args=[str(org_id), str(job_id)], queue=queue)
        except Exception:  # broker down: the sweeper will pick the queued job up
            log.warning("queue.publish_failed", job_id=str(job_id), kind=kind)


class RecordingJobQueue:
    """Collects jobs instead of running them (API tests)."""

    def __init__(self) -> None:
        self.jobs: list[tuple[uuid.UUID, uuid.UUID, str]] = []

    def enqueue(self, *, org_id: uuid.UUID, job_id: uuid.UUID, kind: str) -> None:
        self.jobs.append((org_id, job_id, kind))


def build_job_queue(settings: Settings) -> JobQueue:
    return CeleryJobQueue(settings)
