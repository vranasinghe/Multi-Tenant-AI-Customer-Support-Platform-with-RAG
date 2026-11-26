"""Recovery keeps running while both ingestion slots are busy (AUD05-RECOVERY, OPS-BEAT).

Real processes, as Compose runs them: a two-slot ingestion worker, a one-slot maintenance
worker and a beat using the health-recording scheduler. Own database and Redis databases 11
(broker) and 10 (results). Test-only timings as in ``test_ingestion_worker.py``.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from redis import Redis
from sqlalchemy import Engine

from app.core.config import Settings
from tests.integration.api.conftest import Api
from tests.integration.api.mvp_improvement.test_ingestion_worker import (
    API_ROOT,
    _redis,
    job,
    object_store,
    owner_engine,
    parsers,
    send,
    shared_dir,
    status,
    test_database,
    wait_for,
)
from tests.integration.api.test_knowledge_documents import new_bot
from tests.support.database import TestDatabase
from tests.support.file_store import FileObjectStore
from tests.support.rag import scalar

__all__ = ["object_store", "owner_engine", "shared_dir", "test_database"]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "linux", reason="real prefork workers need Linux"),
]

STUCK, SWEEP = 30, 5
BOUND = SWEEP + 10


@pytest.fixture
def broker_settings(api_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CELERY_BROKER_URL", _redis(11))
    monkeypatch.setenv("CELERY_RESULT_BACKEND", _redis(10))
    return api_settings.model_copy(
        update={"celery_broker_url": _redis(11), "celery_result_backend": _redis(10)}
    )


@pytest.fixture
def job_queue(broker_settings: Settings):  # type: ignore[no-untyped-def]
    from app.rag.queue import CeleryJobQueue

    return CeleryJobQueue(broker_settings)


class Stack:
    def __init__(self, env: dict[str, str], directory: Path) -> None:
        self.env = env
        self.directory = directory
        self.processes: dict[str, subprocess.Popen[bytes]] = {}

    def _start(self, name: str, *args: str) -> None:
        log = (self.directory / f"{name}.log").open("w")
        self.processes[name] = subprocess.Popen(  # noqa: S603 - fixed test command
            [sys.executable, "-m", "celery", "-A", "tests.support.worker_app", *args],
            cwd=API_ROOT,
            env=self.env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def log(self, name: str) -> str:
        return (self.directory / f"{name}.log").read_text(errors="replace")

    def worker(self, name: str, queues: str, concurrency: int) -> None:
        self._start(
            name,
            "worker",
            f"--queues={queues}",
            f"--concurrency={concurrency}",
            "--loglevel=INFO",
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            f"--hostname={name}@testhost",
        )
        wait_for(lambda: "ready." in self.log(name), 30, f"{name} to start")

    def beat(self) -> None:
        self._start(
            "beat",
            "beat",
            "--scheduler=app.workers.health:HeartbeatScheduler",
            f"--schedule={self.directory / 'beat.schedule'}",
            "--loglevel=INFO",
        )

    def health(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603 - fixed test command
            [sys.executable, "-m", "app.workers.health", *args],
            cwd=API_ROOT,
            env=self.env,
            check=False,  # the exit status is the answer
            capture_output=True,
            text=True,
            timeout=30,
        )

    def stop(self, name: str) -> None:
        process = self.processes.pop(name)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


@pytest.fixture
def stack(
    test_database: TestDatabase, owner_engine: Engine, shared_dir: Path, api_settings: Settings
) -> Iterator[Stack]:
    Redis.from_url(_redis(11)).flushdb()
    Redis.from_url(_redis(10)).flushdb()
    with owner_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE ingestion_jobs SET status = 'failed' WHERE status IN ('queued', 'processing')"
        )
        connection.exec_driver_sql("DELETE FROM storage_deletions")
    env = {
        **os.environ,
        "APP_ENV": "test",
        "LOG_FORMAT": "json",
        "LOG_LEVEL": "INFO",
        "DATABASE_URL": test_database.app_url.render_as_string(hide_password=False),
        "REDIS_URL": _redis(11),
        "CELERY_BROKER_URL": _redis(11),
        "CELERY_RESULT_BACKEND": _redis(10),
        "STORAGE_BACKEND": "memory",
        "LLM_PROVIDER": "disabled",
        "EMBEDDING_PROVIDER": "hash",
        "EMBEDDING_MODEL": api_settings.embedding_model,
        "CHUNK_SIZE_TOKENS": "60",
        "CHUNK_OVERLAP_TOKENS": "10",
        "TEST_OBJECT_DIR": str(shared_dir / "objects"),
        "INGEST_STUCK_AFTER_SECONDS": str(STUCK),
        "INGEST_SWEEP_INTERVAL_SECONDS": str(SWEEP),
        "PARSER_WALL_SECONDS": "60",
        "BEAT_HEARTBEAT_FILE": str(shared_dir / "beat-heartbeat"),
    }
    running = Stack(env, shared_dir)
    yield running
    for name in list(running.processes):
        running.stop(name)
    out = os.environ.get("AUDIT_OUTPUT_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        for log in shared_dir.glob("*.log"):
            (Path(out) / f"maintenance-{log.name}").write_text(log.read_text(errors="replace"))
    for pid in parsers():
        os.kill(pid, signal.SIGKILL)


def test_recovery_runs_while_both_ingestion_slots_are_busy(
    api: Api,
    stack: Stack,
    object_store: FileObjectStore,
) -> None:
    stack.worker("ingest", "default,ingest,crawl", 2)
    stack.worker("maintenance", "maintenance", 1)
    tenants = [api.signup() for _ in range(3)]
    bots = [new_bot(owner) for owner in tenants]
    for owner, bot in zip(tenants[:2], bots[:2], strict=True):
        send(owner, bot, "HOSTILE:sleep:60")
    wait_for(lambda: len(parsers()) == 2, 20, "both ingestion slots to be occupied")

    # A job whose worker was hard-killed, and an original nobody wants any more.
    stale = send(tenants[2], bots[2], "The worker holding this job was killed.")
    with api.owner_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE ingestion_jobs SET status = 'processing', attempt = max_attempts, "
            "started_at = now() - interval '1 hour', heartbeat_at = now() - interval '1 hour' "
            "WHERE document_id = %(d)s",
            {"d": stale},
        )
    key = f"orgs/{tenants[2].org_id}/abandoned/{uuid.uuid4().hex}"
    object_store.put(key, b"unwanted", content_type="text/plain")
    with api.owner_engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO storage_deletions (id, org_id, storage_key) VALUES (%(i)s, %(o)s, %(k)s)",
            {"i": uuid.uuid4(), "o": tenants[2].org_id, "k": key},
        )

    started = time.monotonic()
    stack.beat()
    wait_for(lambda: status(api, stale) == "failed", BOUND, "the stuck job to be recovered")
    wait_for(
        lambda: (
            not scalar(
                api.owner_engine,
                "SELECT count(*) FROM storage_deletions WHERE storage_key = :k",
                k=key,
            )
        ),
        BOUND,
        "the abandoned object to be purged",
    )
    seconds = time.monotonic() - started

    assert not object_store._path(key).exists()
    assert job(api, stale)["error_code"] == "internal_error"
    assert len(parsers()) == 2  # the ingestion slots were busy all along
    # Nobody else's running work was touched.
    assert (
        scalar(api.owner_engine, "SELECT count(*) FROM ingestion_jobs WHERE status = 'processing'")
        == 2
    )
    out = os.environ.get("AUDIT_OUTPUT_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / "maintenance-busy-slots.json").write_text(
            json.dumps({"recovery_seconds": seconds, "bound_seconds": BOUND})
        )


def test_scheduler_and_consumer_health_are_reported_separately(stack: Stack) -> None:
    stack.env["BEAT_HEARTBEAT_MAX_AGE_SECONDS"] = "12"
    stack.env["MAINTENANCE_NODE"] = "maintenance@testhost"
    assert stack.health("beat").returncode == 1
    assert stack.health("maintenance").returncode == 1

    stack.worker("maintenance", "maintenance", 1)
    stack.beat()
    # The first sweep is due as soon as beat starts, so progress shows without a full interval.
    wait_for(lambda: stack.health("beat").returncode == 0, SWEEP, "the first published sweep")
    wait_for(lambda: "succeeded in" in stack.log("maintenance"), 10, "the sweep to run")
    assert stack.health("maintenance").returncode == 0

    stack.stop("beat")
    wait_for(lambda: stack.health("beat").returncode == 1, 30, "the stopped scheduler to show")
    assert stack.health("maintenance").returncode == 0  # the consumer itself is fine

    stack.stop("maintenance")
    result = stack.health("maintenance")
    assert result.returncode == 1 and "did not answer" in result.stdout
