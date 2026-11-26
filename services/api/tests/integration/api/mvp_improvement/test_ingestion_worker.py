"""AUD-05 against a real, disposable Celery worker: time limits, worker loss, restart, fairness.

Isolated from every other worker: its own database, Redis databases 13 (broker) and 12 (results)
and its own process group. Test-only timings, shortened from the runtime defaults:

=============================  ======  =======
setting                        test    default
=============================  ======  =======
INGEST_STUCK_AFTER_SECONDS     30      900
INGEST_SWEEP_INTERVAL_SECONDS  5       120
INGEST_SOFT_TIME_LIMIT_SECONDS 2-60    120
INGEST_HARD_TIME_LIMIT_SECONDS 4-90    180
PARSER_WALL_SECONDS            6-60    60
=============================  ======  =======
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from redis import Redis
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.rag.queue import CeleryJobQueue
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import (
    docs_path,
    get_doc,
    new_bot,
    search,
    upload,
)
from tests.support.database import TestDatabase, temporary_database
from tests.support.file_store import FileObjectStore
from tests.support.rag import rows, scalar

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "linux", reason="real prefork workers need Linux"),
]

API_ROOT = Path(__file__).resolve().parents[4]
STUCK, SWEEP = 30, 5
RECOVERY_BOUND = STUCK + SWEEP + 5
TEXT = "Express shipping takes one to two business days and costs extra at checkout."


@pytest.fixture(scope="module")
def test_database() -> Iterator[TestDatabase]:
    """A private database: the real sweeper looks across every organization."""
    # Migrating runs Alembic's fileConfig, which disables every logger that already exists and
    # would silence the log-hygiene tests that run later in the same process.
    disabled = {
        name: logger.disabled
        for name, logger in logging.root.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)
    }
    with temporary_database() as database:
        for name, was_disabled in disabled.items():
            logging.getLogger(name).disabled = was_disabled
        yield database


@pytest.fixture(scope="module")
def owner_engine(test_database: TestDatabase) -> Iterator[Engine]:
    engine = create_engine(test_database.owner_url)
    yield engine
    engine.dispose()


def _redis(database: int) -> str:
    base = make_url(os.environ["REDIS_URL"])
    return base.set(database=str(database)).render_as_string(hide_password=False)


@pytest.fixture
def shared_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="a5-worker-") as directory:
        yield Path(directory)


@pytest.fixture
def object_store(shared_dir: Path) -> FileObjectStore:
    return FileObjectStore(shared_dir / "objects")


@pytest.fixture
def broker_settings(api_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Settings:
    # Celery prefers these variables over the app's own settings: without them the API under
    # test would publish to whichever broker the surrounding environment names.
    monkeypatch.setenv("CELERY_BROKER_URL", _redis(13))
    monkeypatch.setenv("CELERY_RESULT_BACKEND", _redis(12))
    return api_settings.model_copy(
        update={"celery_broker_url": _redis(13), "celery_result_backend": _redis(12)}
    )


@pytest.fixture
def job_queue(broker_settings: Settings) -> CeleryJobQueue:
    return CeleryJobQueue(broker_settings)


class Worker:
    def __init__(self, env: dict[str, str], directory: Path) -> None:
        name = f"a5-{uuid.uuid4().hex[:6]}"
        self.log_path = directory / f"{name}.log"
        self._log = self.log_path.open("w")
        self.process = subprocess.Popen(  # noqa: S603 - fixed test command
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "tests.support.worker_app",
                "worker",
                "--beat",
                f"--schedule={directory / (name + '.schedule')}",
                # One worker stands for both consumers here; Compose gives ``maintenance`` its own
                # (test_maintenance_worker.py covers that separation).
                "--queues=default,ingest,crawl,maintenance",
                "--concurrency=2",
                "--loglevel=INFO",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                f"--hostname={name}@%h",
            ],
            cwd=API_ROOT,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        wait_for(lambda: "ready." in self.log(), 30, "the worker to start")

    def log(self) -> str:
        return self.log_path.read_text(errors="replace")

    def kill(self) -> None:
        """SIGKILL the worker and its pool, as a container stop after the grace period would."""
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait(timeout=10)
        self._log.close()
        out = os.environ.get("AUDIT_OUTPUT_DIR")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out) / self.log_path.name).write_text(self.log())


@pytest.fixture
def start_worker(
    test_database: TestDatabase, owner_engine: Engine, shared_dir: Path, api_settings: Settings
) -> Iterator[Callable[..., Worker]]:
    Redis.from_url(_redis(13)).flushdb()
    Redis.from_url(_redis(12)).flushdb()
    with owner_engine.begin() as connection:  # nothing left over may reach this worker
        connection.exec_driver_sql(
            "UPDATE ingestion_jobs SET status = 'failed' WHERE status IN ('queued', 'processing')"
        )
    workers: list[Worker] = []

    def start(**settings: int) -> Worker:
        env = {
            **os.environ,
            "APP_ENV": "test",
            "LOG_FORMAT": "json",
            "LOG_LEVEL": "INFO",
            "DATABASE_URL": test_database.app_url.render_as_string(hide_password=False),
            "REDIS_URL": _redis(13),
            "CELERY_BROKER_URL": _redis(13),
            "CELERY_RESULT_BACKEND": _redis(12),
            "STORAGE_BACKEND": "memory",
            "LLM_PROVIDER": "disabled",
            "EMBEDDING_PROVIDER": "hash",
            "EMBEDDING_MODEL": api_settings.embedding_model,
            "CHUNK_SIZE_TOKENS": "60",
            "CHUNK_OVERLAP_TOKENS": "10",
            "TEST_OBJECT_DIR": str(shared_dir / "objects"),
            "INGEST_STUCK_AFTER_SECONDS": str(STUCK),
            "INGEST_SWEEP_INTERVAL_SECONDS": str(SWEEP),
            "INGEST_RETRY_BASE_SECONDS": "0",
            "INGEST_DEFER_SECONDS": "1",
            **{name.upper(): str(value) for name, value in settings.items()},
        }
        workers.append(Worker(env, shared_dir))
        return workers[-1]

    yield start
    for worker in workers:
        worker.kill()
    for pid in parsers():
        os.kill(pid, signal.SIGKILL)


def parsers() -> dict[int, int]:
    """Running parser children of the test worker: ``{pid: parent pid}``."""
    found: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes()
            state, ppid = (entry / "stat").read_text().rsplit(")", 1)[1].split()[:2]
        except OSError:
            continue
        if b"tests.support.hostile_parser\x00by-content" in command and state not in {"Z", "X"}:
            found[int(entry.name)] = int(ppid)
    return found


def alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in {"Z", "X"}


def wait_for(predicate: Callable[[], Any], timeout: float, what: str) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    pytest.fail(f"timed out after {timeout}s waiting for {what}")


def send(owner: Actor, bot: str, text: str) -> str:
    response = upload(owner, bot, f"{uuid.uuid4().hex}.txt", text.encode(), "text/plain")
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def job(api: Api, document_id: str) -> dict[str, Any]:
    [row] = rows(
        api.owner_engine,
        "SELECT status, attempt, error_code, "
        "extract(epoch FROM started_at - queued_at) AS waited, "
        "extract(epoch FROM finished_at - started_at) AS processed "
        "FROM ingestion_jobs WHERE document_id = :d ORDER BY id DESC LIMIT 1",
        d=document_id,
    )
    return dict(row._mapping)


def status(api: Api, document_id: str) -> str:
    return str(
        scalar(api.owner_engine, "SELECT status FROM documents WHERE id = :d", d=document_id)
    )


def is_ready(api: Api, document_id: str) -> bool:
    return status(api, document_id) == "ready"


def versions(api: Api, document_id: str) -> list[int]:
    return [
        v
        for (v,) in rows(
            api.owner_engine,
            "SELECT DISTINCT document_version FROM document_chunks WHERE document_id = :d",
            d=document_id,
        )
    ]


def evidence(name: str, data: dict[str, Any]) -> None:
    out = os.environ.get("AUDIT_OUTPUT_DIR")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.json").write_text(json.dumps(data, indent=2, default=float))


# ---------------------------------------------------------------- time limits


def test_the_soft_limit_stops_the_parser_and_records_a_visible_failure(
    api: Api, start_worker: Callable[..., Worker], api_settings: Settings
) -> None:
    api_settings.ingest_max_attempts = 1  # recorded on the job when the API creates it
    worker = start_worker(ingest_soft_time_limit_seconds=3, ingest_hard_time_limit_seconds=20)
    owner = api.signup()
    bot = new_bot(owner)

    doc = send(owner, bot, "HOSTILE:sleep:60")
    [parser] = wait_for(lambda: list(parsers()), 15, "the parser to start")
    started = time.monotonic()

    wait_for(lambda: status(api, doc) == "failed", 15, "the soft limit")

    elapsed = time.monotonic() - started
    assert job(api, doc)["error_code"] == "task_timeout"
    assert "Soft time limit (3s) exceeded" in worker.log()
    assert not alive(parser) and versions(api, doc) == []
    healthy = send(owner, bot, TEXT)  # the worker and the tenant's permit are both free again
    wait_for(lambda: status(api, healthy) == "ready", 10, "a normal document afterwards")
    evidence("soft-limit", {"parser_pid": parser, "seconds_until_failed": elapsed})


def test_the_hard_limit_kills_the_pool_process_and_the_sweeper_recovers(
    api: Api, start_worker: Callable[..., Worker], api_settings: Settings
) -> None:
    api_settings.ingest_max_attempts = 1
    worker = start_worker(ingest_soft_time_limit_seconds=2, ingest_hard_time_limit_seconds=4)
    owner = api.signup()
    bot = new_bot(owner)

    doc = send(owner, bot, f"HOSTILE-IGNORE-SOFT-LIMIT {TEXT}")
    wait_for(lambda: "Hard time limit (4s) exceeded" in worker.log(), 20, "the hard limit")
    killed = time.monotonic()
    assert job(api, doc)["status"] == "processing"  # nothing ran in the killed process

    wait_for(lambda: status(api, doc) == "failed", RECOVERY_BOUND, "the sweeper")

    recovery = time.monotonic() - killed
    assert recovery <= RECOVERY_BOUND
    final = job(api, doc)
    assert (final["status"], final["error_code"]) == ("failed", "internal_error")
    assert versions(api, doc) == []
    healthy = send(owner, bot, TEXT)
    wait_for(lambda: status(api, healthy) == "ready", 15, "a normal document afterwards")
    evidence("hard-limit", {"recovery_seconds": recovery, "bound_seconds": RECOVERY_BOUND})


# ---------------------------------------------------------------- worker loss and restart


def test_losing_the_pool_process_cleans_up_and_retries_without_losing_the_published_version(
    api: Api, start_worker: Callable[..., Worker], shared_dir: Path
) -> None:
    worker = start_worker()
    owner = api.signup()
    bot = new_bot(owner)
    doc = send(owner, bot, f"HOSTILE:hang-on-call:2:{shared_dir / 'calls'}\n{TEXT}")
    wait_for(lambda: status(api, doc) == "ready", 20, "the first version")
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc}/reprocess").status_code == 200
    # The marker proves this parse reached its behaviour; the process alone may still be starting.
    wait_for((shared_dir / "calls.2").exists, 15, "the reindex parse")
    [(parser, pool_process)] = parsers().items()
    assert pool_process != worker.process.pid

    os.kill(pool_process, signal.SIGKILL)
    killed = time.monotonic()
    wait_for(lambda: not alive(parser), 2, "the orphaned parser to die")
    cleanup = time.monotonic() - killed

    assert job(api, doc)["status"] == "processing" and versions(api, doc) == [1]
    assert search(owner, bot, "express shipping")
    wait_for(lambda: status(api, doc) == "ready", RECOVERY_BOUND, "recovery")
    recovery = time.monotonic() - killed

    final = job(api, doc)
    assert (final["status"], final["attempt"]) == ("succeeded", 2)
    assert versions(api, doc) == [2] and get_doc(owner, bot, doc)["version"] == 2
    assert "WorkerLostError" in worker.log()
    evidence(
        "pool-process-loss",
        {
            "parser_pid": parser,
            "pool_pid": pool_process,
            "parser_gone_seconds": cleanup,
            "recovery_seconds": recovery,
            "bound_seconds": RECOVERY_BOUND,
        },
    )


def test_a_restarted_worker_recovers_the_job_of_a_killed_one(
    api: Api, start_worker: Callable[..., Worker], shared_dir: Path
) -> None:
    first = start_worker()
    owner = api.signup()
    bot = new_bot(owner)
    doc = send(owner, bot, f"HOSTILE:hang-on-call:1:{shared_dir / 'calls'}\n{TEXT}")
    wait_for((shared_dir / "calls.1").exists, 20, "the parse")
    [parser] = parsers()

    first.kill()
    killed = time.monotonic()
    wait_for(lambda: not alive(parser), 2, "the orphaned parser to die")
    assert job(api, doc)["status"] == "processing"
    start_worker()

    wait_for(lambda: status(api, doc) == "ready", RECOVERY_BOUND, "recovery after restart")

    recovery = time.monotonic() - killed
    final = job(api, doc)
    assert recovery <= RECOVERY_BOUND
    assert (final["status"], final["attempt"]) == ("succeeded", 2)
    assert versions(api, doc) == [1] and parsers() == {}
    evidence("worker-restart", {"recovery_seconds": recovery, "bound_seconds": RECOVERY_BOUND})


# ---------------------------------------------------------------- fairness and duplicates


def test_one_tenants_slow_job_does_not_delay_another_tenant(
    api: Api, start_worker: Callable[..., Worker]
) -> None:
    start_worker(parser_wall_seconds=8)
    tenant_a, tenant_b = api.signup(), api.signup()
    bot_a, bot_b = new_bot(tenant_a), new_bot(tenant_b)
    # Warm both pool processes so the measurement is not dominated by first-task imports.
    for owner, bot in ((tenant_a, bot_a), (tenant_b, bot_b)):
        warm = send(owner, bot, f"warm up {uuid.uuid4()}")
        wait_for(partial(is_ready, api, warm), 20, "warm-up")
    slow = send(tenant_a, bot_a, "HOSTILE:sleep:60")
    wait_for(lambda: list(parsers()), 15, "tenant A's slow parser")
    queued_behind = send(tenant_a, bot_a, f"Tenant A's second document. {TEXT}")

    submitted = time.monotonic()
    normal = send(tenant_b, bot_b, f"Tenant B's document. {TEXT}")
    wait_for(lambda: status(api, normal) == "ready", 5, "tenant B to be ready")
    b_ready = time.monotonic() - submitted

    b = job(api, normal)
    assert b["waited"] <= 2, b
    assert b_ready <= 5
    assert job(api, slow)["status"] == "processing"  # B did not wait for A
    waiting = job(api, queued_behind)
    assert (waiting["status"], waiting["attempt"], waiting["error_code"]) == ("queued", 0, None)

    wait_for(lambda: status(api, slow) == "failed", 15, "tenant A's parser deadline")
    a_failed = time.monotonic()
    wait_for(lambda: status(api, queued_behind) == "ready", 8, "tenant A's second document")
    a_follow_up = time.monotonic() - a_failed

    assert job(api, slow)["error_code"] == "parse_timeout"
    assert job(api, queued_behind)["attempt"] == 1
    assert status(api, normal) == "ready" and job(api, normal)["status"] == "succeeded"
    assert search(tenant_b, bot_b, "express shipping")
    evidence(
        "fairness",
        {
            "tenant_b_queue_wait_seconds": b["waited"],
            "tenant_b_processing_seconds": b["processed"],
            "tenant_b_submit_to_ready_seconds": b_ready,
            "tenant_a_slow_processing_seconds": job(api, slow)["processed"],
            "tenant_a_second_ready_after_first_failed_seconds": a_follow_up,
        },
    )


def test_duplicate_deliveries_to_a_real_worker_create_no_duplicate_chunks(
    api: Api, start_worker: Callable[..., Worker], job_queue: CeleryJobQueue
) -> None:
    worker = start_worker()
    owner = api.signup()
    bot = new_bot(owner)
    doc = send(owner, bot, TEXT)
    job_id = scalar(api.owner_engine, "SELECT id FROM ingestion_jobs WHERE document_id = :d", d=doc)
    for _ in range(3):
        job_queue.enqueue(org_id=uuid.UUID(owner.org_id), job_id=job_id, kind="process_document")

    wait_for(lambda: worker.log().count("succeeded in") >= 4, 20, "all four deliveries")

    assert job(api, doc)["attempt"] == 1 and versions(api, doc) == [1]
    assert (
        scalar(
            api.owner_engine, "SELECT count(*) FROM document_chunks WHERE document_id = :d", d=doc
        )
        == get_doc(owner, bot, doc)["chunk_count"]
    )
