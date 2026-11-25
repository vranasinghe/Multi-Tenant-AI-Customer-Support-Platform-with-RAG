"""Celery signal handlers: structured logging and request-id propagation API → worker."""

from __future__ import annotations

from typing import Any

import structlog
from celery import Task
from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import configure_logging

REQUEST_ID_HEADER = "request_id"


@setup_logging.connect
def configure_worker_logging(**_: Any) -> None:
    """Replace Celery's logging setup with ours (same JSON/console format as the API)."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


@before_task_publish.connect
def propagate_request_id(headers: dict[str, Any] | None = None, **_: Any) -> None:
    """Copy the current request id (if any) into the task message headers."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    if request_id and headers is not None:
        headers.setdefault(REQUEST_ID_HEADER, request_id)


@task_prerun.connect
def bind_task_context(
    task_id: str | None = None, task: Task[Any, Any] | None = None, **_: Any
) -> None:
    structlog.contextvars.clear_contextvars()
    request_id = getattr(task.request, REQUEST_ID_HEADER, None) if task is not None else None
    structlog.contextvars.bind_contextvars(
        task_id=task_id,
        task_name=task.name if task is not None else None,
        request_id=request_id,
    )


@task_postrun.connect
def clear_task_context(**_: Any) -> None:
    structlog.contextvars.clear_contextvars()
