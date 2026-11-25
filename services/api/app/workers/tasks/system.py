"""Infrastructure tasks used for health checks and smoke tests."""

from __future__ import annotations

import structlog

from app.core.logging import get_logger
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="system.ping")
def ping() -> dict[str, str | None]:
    """Round-trip probe: proves broker delivery, worker execution and result backend."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    log.info("system.ping")
    return {"pong": "ok", "request_id": request_id}
