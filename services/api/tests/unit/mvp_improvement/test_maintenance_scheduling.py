"""Recovery work has its own queue, and scheduler and consumer health mean what they say."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from celery.beat import PersistentScheduler, SchedulingError

from app.workers import health
from app.workers.celery_app import QUEUES, celery_app

# ---------------------------------------------------------------- routing


def test_the_sweeper_has_its_own_queue() -> None:
    assert "maintenance" in QUEUES
    assert celery_app.amqp.router.route({}, "ingest.sweep")["queue"].name == "maintenance"
    for task in ("ingest.process_document", "ingest.crawl_source"):
        assert celery_app.amqp.router.route({}, task)["queue"].name != "maintenance"


def test_a_sweep_nobody_ran_expires_instead_of_piling_up() -> None:
    entry = celery_app.conf.beat_schedule["ingest-sweep"]

    assert entry["options"]["expires"] == entry["schedule"]


# ---------------------------------------------------------------- scheduler


@pytest.fixture
def heartbeat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "beat-heartbeat"
    monkeypatch.setenv("BEAT_HEARTBEAT_FILE", str(path))
    return path


def publish(monkeypatch: pytest.MonkeyPatch, outcome: Exception | None) -> None:
    def apply_async(self: Any, entry: Any, **_: Any) -> str:
        if outcome is not None:
            raise outcome
        return "sent"

    monkeypatch.setattr(PersistentScheduler, "apply_async", apply_async)


def scheduler() -> health.HeartbeatScheduler:
    return object.__new__(health.HeartbeatScheduler)


def test_a_published_task_records_scheduler_progress(
    heartbeat: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(monkeypatch, None)

    assert scheduler().apply_async(object()) == "sent"
    assert heartbeat.exists()


def test_a_failed_publish_records_no_progress(
    heartbeat: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(monkeypatch, SchedulingError("broker unreachable"))

    with pytest.raises(SchedulingError):
        scheduler().apply_async(object())
    assert not heartbeat.exists()


def test_beat_is_healthy_only_while_it_keeps_publishing(heartbeat: Path) -> None:
    assert "no task published" in str(health.beat_problem(max_age=60))
    heartbeat.touch()
    assert health.beat_problem(max_age=60) is None

    os.utime(heartbeat, (1_000, 1_000))

    assert "seconds ago" in str(health.beat_problem(max_age=60))


def test_the_allowed_age_follows_the_sweep_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INGEST_SWEEP_INTERVAL_SECONDS", raising=False)
    assert health.beat_max_age() == 300
    monkeypatch.setenv("INGEST_SWEEP_INTERVAL_SECONDS", "600")
    assert health.beat_max_age() == 1260


# ---------------------------------------------------------------- consumer

NODE = "maintenance@host"


def replies(queues: list[str] | None = None, started: list[float] | None = None) -> tuple[Any, Any]:
    names = None if queues is None else {NODE: [{"name": name} for name in queues]}
    return names, {NODE: [{"name": "ingest.sweep", "time_start": at} for at in started or []]}


@pytest.mark.parametrize(
    ("queues", "started", "problem"),
    [
        (["maintenance"], [], None),
        (["maintenance"], [9_990.0], None),
        (None, [], "did not answer"),
        (["default"], [], "not consuming"),
        (["maintenance"], [9_000.0], "running for"),
    ],
)
def test_consumer_health(
    queues: list[str] | None, started: list[float], problem: str | None
) -> None:
    active_queues, active = replies(queues, started)

    found = health.consumer_problem(NODE, active_queues, active, now=10_000.0, max_task_age=600)

    assert found is None if problem is None else problem in str(found)
