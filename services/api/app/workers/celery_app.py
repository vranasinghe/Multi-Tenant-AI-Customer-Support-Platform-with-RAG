"""Celery application.

Start a worker with:
    celery -A app.workers.celery_app worker -Q default,ingest,crawl,chat_out,billing

Postgres stays the source of truth for job state; Celery is only the transport (ADR-007).
"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import Settings, get_settings

#: Queues from docs/ARCHITECTURE.md §13.
QUEUES = ("default", "ingest", "crawl", "chat_out", "billing")


def create_celery_app(settings: Settings) -> Celery:
    settings.validate_provider_transport()
    app = Celery(
        settings.app_name,
        broker=settings.broker_url,
        backend=settings.result_backend_url,
        include=["app.workers.tasks.system", "app.workers.tasks.ingest"],
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
            "ingest.sweep": {"queue": "default"},
        },
        beat_schedule={
            "ingest-sweep": {"task": "ingest.sweep", "schedule": 120.0},
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
