"""Health of the scheduler and of the maintenance consumer, reported separately.

``python -m app.workers.health beat``         beat has published a task recently
``python -m app.workers.health maintenance``  the maintenance consumer answers, consumes its
                                              queue and has no task stuck on it

A running process proves neither. Beat records a heartbeat only after the broker accepted a task,
and the consumer is asked through the broker. Exit status 0 means healthy; otherwise one line
says why.
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from celery.beat import PersistentScheduler

MAINTENANCE_QUEUE = "maintenance"
SWEEP_ENTRY = "ingest-sweep"
#: No sweep should take this long: a hundred deletions, each bounded by the storage timeouts.
MAX_MAINTENANCE_TASK_SECONDS = 600.0


def heartbeat_file() -> Path:
    default = Path(tempfile.gettempdir()) / "celerybeat-heartbeat"
    return Path(os.environ.get("BEAT_HEARTBEAT_FILE") or default)


def beat_max_age() -> float:
    """Two missed sweeps and a minute of slack."""
    if override := os.environ.get("BEAT_HEARTBEAT_MAX_AGE_SECONDS"):
        return float(override)
    return 2 * float(os.environ.get("INGEST_SWEEP_INTERVAL_SECONDS") or 120) + 60


class HeartbeatScheduler(PersistentScheduler):
    """The default scheduler, recording each task the broker accepted.

    The sweep is due as soon as beat starts: a restart recovers stuck work at once, and health
    shows real progress without waiting a whole interval.
    """

    def setup_schedule(self) -> None:
        heartbeat_file().unlink(missing_ok=True)  # progress of an earlier process says nothing
        super().setup_schedule()
        entry = self.schedule.get(SWEEP_ENTRY)
        if entry is not None:
            interval = float(self.app.conf.beat_schedule[SWEEP_ENTRY]["schedule"])
            entry.last_run_at = self.app.now() - timedelta(seconds=interval)

    def apply_async(self, entry: Any, producer: Any = None, advance: bool = True, **kw: Any) -> Any:
        # Raises when the broker did not take the task; then no progress is recorded.
        result = super().apply_async(entry, producer=producer, advance=advance, **kw)
        heartbeat_file().touch()
        return result


def beat_problem(max_age: float) -> str | None:
    try:
        age = time.time() - heartbeat_file().stat().st_mtime
    except OSError:
        return "beat: no task published since it started"
    if age > max_age:
        return f"beat: last task published {age:.0f} seconds ago (limit {max_age:.0f})"
    return None


def consumer_problem(
    node: str,
    active_queues: dict[str, Any] | None,
    active: dict[str, Any] | None,
    *,
    now: float,
    max_task_age: float,
) -> str | None:
    queues = (active_queues or {}).get(node)
    if queues is None:
        return f"maintenance: {node} did not answer"
    if MAINTENANCE_QUEUE not in {queue["name"] for queue in queues}:
        return f"maintenance: {node} is not consuming the {MAINTENANCE_QUEUE} queue"
    for task in (active or {}).get(node, []):
        started = task.get("time_start")
        if started is not None and now - started > max_task_age:
            return f"maintenance: {task['name']} has been running for {now - started:.0f} seconds"
    return None


def maintenance_problem() -> str | None:
    from app.workers.celery_app import celery_app  # noqa: PLC0415 - beat needs no settings

    node = os.environ.get("MAINTENANCE_NODE") or f"maintenance@{socket.gethostname()}"
    inspect = celery_app.control.inspect([node], timeout=5)
    try:
        queues = inspect.active_queues()
        active = inspect.active()
    except Exception as exc:  # broker unreachable: unhealthy, without printing its address
        return f"maintenance: broker request failed ({type(exc).__name__})"
    return consumer_problem(
        node, queues, active, now=time.time(), max_task_age=MAX_MAINTENANCE_TASK_SECONDS
    )


def main(argv: list[str] | None = None) -> int:
    which = (argv if argv is not None else sys.argv[1:])[:1]
    if which == ["beat"]:
        problem = beat_problem(beat_max_age())
    elif which == ["maintenance"]:
        problem = maintenance_problem()
    else:
        problem = "usage: python -m app.workers.health beat|maintenance"
    sys.stdout.write((problem or "healthy") + "\n")
    return 1 if problem else 0


if __name__ == "__main__":
    raise SystemExit(main())
