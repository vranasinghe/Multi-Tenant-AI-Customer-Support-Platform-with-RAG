"""Celery application.

Start a worker with:
    celery -A app.workers.celery_app worker -Q default,ingest,crawl,chat_out,billing

Postgres stays the source of truth for job state; Celery is only the transport (ADR-007).
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import Settings, get_settings
from app.rag import parser_process
from app.workers.health import MAINTENANCE_QUEUE, SWEEP_ENTRY

#: Queues from docs/ARCHITECTURE.md §13. ``maintenance`` has its own consumer, so recovery never
#: waits behind the ingestion jobs it is there to recover.
QUEUES = ("default", "ingest", "crawl", "chat_out", "billing", MAINTENANCE_QUEUE)


def create_celery_app(settings: Settings) -> Celery:
    settings.validate_provider_transport()
    if settings.app_env in {"staging", "production"} and not parser_process.containment_supported():
        msg = "Parser containment requires Linux; refusing to start a deployed worker"
        raise RuntimeError(msg)
    app = Celery(
        settings.app_name,
        broker=settings.broker_url,
        backend=settings.result_backend_url,
        include=[
            "app.workers.tasks.system",
            "app.workers.tasks.ingest",
            "app.workers.tasks.analytics",
        ],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_default_queue="default",
        task_queues=[Queue(name) for name in QUEUES],
        task_routes={
            "system.*": {"queue": "default"},
            "ingest.process_document": {"queue": "ingest"},
            "ingest.crawl_source": {"queue": "crawl"},
            "ingest.sweep": {"queue": MAINTENANCE_QUEUE},
            "analytics.retention": {"queue": "default"},
            "analytics.rollup": {"queue": "default"},
        },
        # Execution limits (prefork pool): soft raises in the task, hard kills the pool process.
        task_annotations={
            "ingest.process_document": {
                "soft_time_limit": settings.ingest_soft_time_limit_seconds,
                "time_limit": settings.ingest_hard_time_limit_seconds,
            },
            "ingest.crawl_source": {
                "soft_time_limit": settings.crawl_soft_time_limit_seconds,
                "time_limit": settings.crawl_hard_time_limit_seconds,
            },
        },
        beat_schedule={
            SWEEP_ENTRY: {
                "task": "ingest.sweep",
                "schedule": settings.ingest_sweep_interval_seconds,
                # A sweep nobody took in time is dropped: the next one does the same work.
                "options": {"expires": settings.ingest_sweep_interval_seconds},
            },
            "analytics-rollup": {"task": "analytics.rollup", "schedule": 3600.0},
            "conversation-retention": {"task": "analytics.retention", "schedule": 86400.0},
        },
        # Reliability: re-deliver tasks whose worker died; tasks must be idempotent.
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": 3600},
        result_expires=3600,
        # Logging is configured by app.workers.signals so worker logs match the API format.
        worker_hijack_root_logger=False,
        worker_send_task_events=False,
    )
    return app


celery_app = create_celery_app(get_settings())

# Connect signal handlers (logging, request-id propagation). Imported for side effects.
from app.workers import signals  # noqa: E402

__all__ = ["QUEUES", "celery_app", "create_celery_app", "signals"]
