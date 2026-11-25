from __future__ import annotations

import structlog

from app.workers.celery_app import QUEUES, celery_app
from app.workers.signals import propagate_request_id
from app.workers.tasks.system import ping


def test_queues_and_reliability_settings() -> None:
    conf = celery_app.conf

    assert {queue.name for queue in conf.task_queues} == set(QUEUES)
    assert conf.task_default_queue == "default"
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.accept_content == ["json"]


def test_ping_task_is_registered_and_routed_to_default() -> None:
    assert "system.ping" in celery_app.tasks
    assert celery_app.amqp.router.route({}, "system.ping")["queue"].name == "default"


def test_ping_executes_locally() -> None:
    result = ping.apply().get()

    assert result["pong"] == "ok"


def test_request_id_is_copied_into_task_headers() -> None:
    headers: dict[str, object] = {}
    structlog.contextvars.bind_contextvars(request_id="req-from-api")
    try:
        propagate_request_id(headers=headers)
    finally:
        structlog.contextvars.clear_contextvars()

    assert headers["request_id"] == "req-from-api"


def test_no_request_id_header_without_context() -> None:
    headers: dict[str, object] = {}
    structlog.contextvars.clear_contextvars()

    propagate_request_id(headers=headers)

    assert "request_id" not in headers
