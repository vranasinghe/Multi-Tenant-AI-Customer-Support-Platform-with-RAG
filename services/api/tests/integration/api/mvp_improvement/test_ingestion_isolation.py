"""AUD-05 job lifecycle: contained parser failures, attempt fencing and per-organization admission.

Workers run in this process against the real database; the parser is a real child process. Real
Celery worker behaviour (time limits, worker loss, restart) is in ``test_ingestion_worker.py``.
"""

from __future__ import annotations

import contextlib
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import Engine

from app.rag import pipeline
from app.rag.crawl_job import run_crawl_job
from app.rag.embeddings import HashingEmbedder
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import Block, ExtractedDocument
from app.rag.maintenance import defer_job, sweep_jobs, wake_next
from app.rag.parser_runner import ParserLimits, ParserRunner
from app.rag.pipeline import JobDeferredError, StaleClaimError, claim_job, run_document_job
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.rag.safe_fetch import SafeFetcher
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import (
    DOCX,
    PDF,
    RETURNS,
    SHIPPING,
    docs_path,
    get_doc,
    new_bot,
    search,
    upload,
)
from tests.support.documents import make_docx, make_pdf
from tests.support.rag import rows, run_jobs, scalar
from tests.support.site import Site, serve

pytestmark = pytest.mark.integration

linux = pytest.mark.skipif(sys.platform != "linux", reason="containment is enforced on Linux")
TXT = "text/plain"
MIB = 1024 * 1024
PAGE = (
    "Standard shipping to the United States takes three to five business days after dispatch. "
) * 5


@pytest.fixture(autouse=True)
def no_job_stays_active(owner_engine: Engine) -> Iterator[None]:
    """The session database is shared and the sweeper counts every organization's jobs."""
    yield
    with owner_engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE ingestion_jobs SET status = 'failed' WHERE status IN ('queued', 'processing')"
        )


@pytest.fixture
def site() -> Any:
    with serve() as s:
        s.text("/robots.txt", "User-agent: *\n")
        s.page("/", "Help", f"<p>Welcome. {PAGE}</p>", links=["/ship"])
        s.page("/ship", "Shipping", f"<p>Shipping page. {PAGE}</p>")
        yield s


@pytest.fixture
def web_fetcher(site: Site) -> SafeFetcher:
    return site.fetcher()


def hostile(mode: str, **limits: Any) -> ParserRunner:
    return ParserRunner(
        ParserLimits(**limits),
        command=("-m", "tests.support.hostile_parser", mode),
        cancel_poll_seconds=0.2,
    )


def queue_upload(
    owner: Actor,
    queue: RecordingJobQueue,
    data: bytes = SHIPPING.encode(),
    name: str = "",
    content_type: str = TXT,
    bot: str | None = None,
) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    bot = bot or new_bot(owner)
    response = upload(owner, bot, name or f"{uuid.uuid4().hex}.txt", data, content_type)
    assert response.status_code == 201, response.text
    org_id, job_id, _ = queue.jobs.pop(0)
    return bot, response.json()["id"], org_id, job_id


def job_row(api: Api, job_id: uuid.UUID) -> Any:
    [row] = rows(
        api.owner_engine,
        "SELECT status, attempt, error_code, queued_at, stats FROM ingestion_jobs WHERE id = :j",
        j=job_id,
    )
    return row


def chunks(api: Api, document_id: str) -> int:
    return int(
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=document_id,
        )
    )


def make_stale(api: Api, job_id: uuid.UUID) -> None:
    api.sql(
        "UPDATE ingestion_jobs SET heartbeat_at = now() - interval '2 hours', "
        "started_at = now() - interval '2 hours' WHERE id = :j",
        j=job_id,
    )


# ---------------------------------------------------------------- successful ingestion


def test_ingestion_keeps_page_and_heading_metadata_and_vector_width(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, pdf_id, org_id, job_id = queue_upload(
        owner, job_queue, make_pdf(["Alpha shipping", "Beta returns"]), "a.pdf", PDF
    )
    assert run_document_job(runtime, org_id, job_id) == "done"
    docx = make_docx([("h1", "Returns"), ("p", "Items can be returned within 30 days.")])
    _, docx_id, org_id, job_id = queue_upload(owner, job_queue, docx, "b.docx", DOCX, bot=bot)
    assert run_document_job(runtime, org_id, job_id) == "done"

    [(page_start, page_end)] = rows(
        api.owner_engine,
        "SELECT min(page_start), max(page_end) FROM document_chunks WHERE document_id = :d",
        d=pdf_id,
    )
    [(heading, width)] = rows(
        api.owner_engine,
        "SELECT heading_path, vector_dims(embedding) FROM document_chunks "
        "WHERE document_id = :d LIMIT 1",
        d=docx_id,
    )
    assert (page_start, page_end, heading, width) == (1, 2, ["Returns"], 1536)


# ---------------------------------------------------------------- contained parser failures


@linux
@pytest.mark.parametrize(
    ("mode", "limits", "code"),
    [
        ("sleep:5", {"wall_seconds": 0.5}, "parse_timeout"),
        ("spin", {"cpu_seconds": 1}, "parse_resource_limit"),
        ("allocate", {"memory_bytes": 256 * MIB}, "parse_resource_limit"),
        ("malformed:not-json", {}, "parse_invalid_output"),
    ],
)
def test_a_parser_limit_gives_a_visible_failed_state_and_publishes_nothing(
    api: Api,
    runtime: Runtime,
    job_queue: RecordingJobQueue,
    mode: str,
    limits: dict[str, Any],
    code: str,
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    healthy, runtime.parser = runtime.parser, hostile(mode, **limits)

    assert run_document_job(runtime, org_id, job_id) == "failed"

    doc = get_doc(owner, bot, doc_id)
    assert (doc["status"], doc["error_code"], doc["job"]["status"]) == ("failed", code, "failed")
    assert doc["job"]["attempt"] == 1  # deterministic: never retried automatically
    assert doc["error_message"] and "Something went wrong" not in doc["error_message"]
    assert chunks(api, doc_id) == 0

    runtime.parser = healthy  # manual reprocessing stays available
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 200
    assert run_jobs(runtime, job_queue) == ["done"]


@linux
def test_a_parser_failure_while_reindexing_keeps_the_published_version(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    assert run_document_job(runtime, org_id, job_id) == "done"
    before = chunks(api, doc_id)
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 200
    org_id, job_id, _ = job_queue.jobs.pop(0)
    runtime.parser = hostile("sleep:5", wall_seconds=0.5)

    assert run_document_job(runtime, org_id, job_id) == "failed"

    doc = get_doc(owner, bot, doc_id)
    assert (doc["status"], doc["version"], chunks(api, doc_id)) == ("failed", 1, before)
    assert search(owner, bot, "express shipping")


@linux
def test_deleting_a_document_during_parsing_cancels_the_parser(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    _, other_id, _, other_job = queue_upload(owner, job_queue, RETURNS.encode(), bot=bot)
    healthy, runtime.parser = runtime.parser, hostile("sleep:30")

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(run_document_job, runtime, org_id, job_id)
        deadline = time.monotonic() + 10
        while job_row(api, job_id)[0] != "processing" and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.5)  # the parser is now running
        started = time.monotonic()
        assert owner.delete(f"{docs_path(owner, bot)}/documents/{doc_id}").status_code == 204
        outcome = running.result(timeout=10)

    assert outcome == "gone" and time.monotonic() - started < 4
    assert chunks(api, doc_id) == 0
    runtime.parser = healthy
    assert run_document_job(runtime, org_id, other_job) == "done"  # the permit was released
    assert chunks(api, other_id) >= 1


# ---------------------------------------------------------------- stale attempts


class TakenOver(HashingEmbedder):
    """While attempt 1 is embedding, the sweeper resets it and attempt 2 finishes the job."""

    def __init__(self, api: Api, runtime: Runtime, job_id: uuid.UUID, org_id: uuid.UUID) -> None:
        super().__init__()
        self.args = (api, runtime, job_id, org_id)
        self.second: str | None = None
        self.then: Exception | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        api, runtime, job_id, org_id = self.args
        if self.second is None:
            make_stale(api, job_id)
            sweep_jobs(runtime, RecordingJobQueue())
            newer = Runtime(**{**vars(runtime), "embedder": HashingEmbedder()})
            self.second = run_document_job(newer, org_id, job_id)
            if self.then is not None:
                raise self.then
        return super().embed_documents(texts)


@pytest.mark.parametrize(
    "then",
    [
        None,
        IngestionError("corrupt", "late permanent failure"),
        TransientIngestionError("embedding_failed", "late transient failure"),
        RuntimeError("late bug"),
    ],
    ids=["publishes-late", "fails-late", "requeues-late", "crashes-late"],
)
def test_a_stale_attempt_cannot_overwrite_a_newer_one(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, then: Exception | None
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    runtime.embedder = stale = TakenOver(api, runtime, job_id, org_id)
    stale.then = then

    first = run_document_job(runtime, org_id, job_id)

    assert (stale.second, first) == ("done", "stale")
    doc = get_doc(owner, bot, doc_id)
    assert (doc["status"], doc["version"], doc["error_code"]) == ("ready", 1, None)
    assert job_row(api, job_id)[:3] == ("succeeded", 2, None)
    assert chunks(api, doc_id) == doc["chunk_count"]


def test_publication_checks_ownership_inside_the_publishing_transaction(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    claim = claim_job(runtime, org_id, job_id)
    assert claim is not None
    api.sql("UPDATE ingestion_jobs SET attempt = attempt + 1 WHERE id = :j", j=job_id)

    with pytest.raises(StaleClaimError):
        pipeline.index_document(
            runtime,
            org_id=org_id,
            chatbot_id=claim.chatbot_id,
            document_id=uuid.UUID(doc_id),
            extracted=ExtractedDocument(blocks=[Block(text="late content")]),
            claim=claim,
            completes_job=True,
        )

    assert chunks(api, doc_id) == 0 and get_doc(owner, bot, doc_id)["version"] == 0


def test_every_transition_of_a_superseded_claim_is_refused(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    claim = claim_job(runtime, org_id, job_id)
    assert claim is not None
    api.sql("UPDATE ingestion_jobs SET attempt = attempt + 1 WHERE id = :j", j=job_id)
    before = job_row(api, job_id)

    with pytest.raises(StaleClaimError):
        pipeline.heartbeat(runtime, claim, "embed")
    assert pipeline.fail_job(runtime, claim, IngestionError("corrupt")) is False
    assert pipeline.requeue_job(runtime, claim, TransientIngestionError("storage_error")) is False

    assert job_row(api, job_id) == before
    assert get_doc(owner, bot, doc_id)["status"] == "queued"  # as the claim left it


def test_the_sweeper_leaves_a_job_that_heartbeated_after_it_was_listed(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = api.signup()
    _, _, org_id, job_id = queue_upload(owner, job_queue)
    assert claim_job(runtime, org_id, job_id) is not None
    make_stale(api, job_id)
    original = runtime.tenant_tx

    def revive_then_open(org: uuid.UUID) -> Any:
        api.sql("UPDATE ingestion_jobs SET heartbeat_at = now() WHERE id = :j", j=job_id)
        return original(org)

    monkeypatch.setattr(runtime, "tenant_tx", revive_then_open, raising=False)

    assert sweep_jobs(runtime, job_queue) == 0
    assert job_row(api, job_id)[0] == "processing"


# ---------------------------------------------------------------- task time limit


def test_a_soft_task_time_limit_is_retried_then_fails_visibly(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    class OutOfTime(HashingEmbedder):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise SoftTimeLimitExceeded

    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    api.sql("UPDATE ingestion_jobs SET max_attempts = 2 WHERE id = :j", j=job_id)
    runtime.embedder = OutOfTime()

    with pytest.raises(TransientIngestionError) as info:
        run_document_job(runtime, org_id, job_id)
    assert info.value.code == "task_timeout" and job_row(api, job_id)[0] == "queued"
    assert run_document_job(runtime, org_id, job_id) == "failed"

    doc = get_doc(owner, bot, doc_id)
    assert (doc["status"], doc["error_code"], chunks(api, doc_id)) == ("failed", "task_timeout", 0)
    assert "too long" in doc["error_message"]


# ---------------------------------------------------------------- per-organization admission


def test_one_organization_runs_one_heavy_job_while_another_proceeds(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    tenant_a, tenant_b = api.signup(), api.signup()
    bot, _, org_a, first = queue_upload(tenant_a, job_queue)
    _, second_doc, _, second = queue_upload(tenant_a, job_queue, RETURNS.encode(), bot=bot)
    _, _, org_b, other = queue_upload(tenant_b, job_queue)
    held = claim_job(runtime, org_a, first)
    assert held is not None

    assert run_document_job(runtime, org_a, second) == "deferred"
    assert run_document_job(runtime, org_b, other) == "done"
    assert job_row(api, second)[:3] == ("queued", 0, None)  # no attempt used, not failed
    for _ in range(10):
        with pytest.raises(JobDeferredError):
            claim_job(runtime, org_a, second)
    assert job_row(api, second)[:3] == ("queued", 0, None)

    pipeline.fail_job(runtime, held, IngestionError("corrupt"))  # releases the permit
    assert run_document_job(runtime, org_a, second) == "done"
    assert chunks(api, second_doc) >= 1


def test_a_redelivery_of_the_running_job_is_skipped_not_deferred(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    _, _, org_id, job_id = queue_upload(owner, job_queue)
    assert claim_job(runtime, org_id, job_id) is not None

    assert run_document_job(runtime, org_id, job_id) == "skipped"


def test_concurrent_claims_admit_exactly_one_job_per_organization(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    jobs = [
        queue_upload(owner, job_queue, f"document number {n} text".encode(), f"{n}.txt", bot=bot)
        for n in range(4)
    ]
    barrier = threading.Barrier(len(jobs))

    def attempt(entry: tuple[str, str, uuid.UUID, uuid.UUID]) -> str:
        barrier.wait(timeout=5)
        try:
            return "claimed" if claim_job(runtime, entry[2], entry[3]) else "skipped"
        except JobDeferredError:
            return "deferred"

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        outcomes = list(pool.map(attempt, jobs))

    assert sorted(outcomes) == ["claimed", "deferred", "deferred", "deferred"]


def test_a_dead_attempt_stops_holding_the_permit_after_the_stuck_threshold(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, _, org_id, dead = queue_upload(owner, job_queue)
    _, _, _, waiting = queue_upload(owner, job_queue, RETURNS.encode(), bot=bot)
    assert claim_job(runtime, org_id, dead) is not None
    make_stale(api, dead)

    assert run_document_job(runtime, org_id, waiting) == "done"


def test_crawls_count_against_the_same_organization_limit(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, site: Site
) -> None:
    owner = api.signup()
    bot, _, org_id, document_job = queue_upload(owner, job_queue)
    response = owner.post(
        f"{docs_path(owner, bot)}/sources", {"url": f"{site.base}/", "confirm_authorized": True}
    )
    assert response.status_code == 201, response.text
    _, crawl_job_id, _ = job_queue.jobs.pop(0)
    runtime.fetcher = site.fetcher()
    assert claim_job(runtime, org_id, document_job) is not None

    assert run_crawl_job(runtime, org_id, crawl_job_id) == "deferred"
    assert job_row(api, crawl_job_id)[:2] == ("queued", 0) and site.requests == []


def test_a_deferred_job_is_woken_when_the_permit_is_free(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, _, org_id, first = queue_upload(owner, job_queue)
    _, _, _, second = queue_upload(owner, job_queue, RETURNS.encode(), bot=bot)
    held = claim_job(runtime, org_id, first)
    assert held is not None
    queued_before = job_row(api, second)[3]
    defer_job(runtime, org_id, second, touch=True)
    assert job_row(api, second)[3] > queued_before  # the sweeper leaves a live chain alone
    assert wake_next(runtime, job_queue, org_id) is False  # permit still held

    pipeline.fail_job(runtime, held, IngestionError("corrupt"))

    assert wake_next(runtime, job_queue, org_id) is True
    assert job_queue.jobs == [(org_id, second, "process_document")]


def test_a_job_waiting_for_its_retry_backoff_is_not_woken_early(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    _, _, org_id, job_id = queue_upload(owner, job_queue)
    claim = claim_job(runtime, org_id, job_id)
    assert claim is not None
    defer_job(runtime, org_id, job_id, touch=False)
    pipeline.requeue_job(runtime, claim, TransientIngestionError("storage_error"))

    assert wake_next(runtime, job_queue, org_id) is False and job_queue.jobs == []


# ---------------------------------------------------------------- website crawls


def start_crawl(
    owner: Actor, queue: RecordingJobQueue, runtime: Runtime, site: Site
) -> tuple[str, uuid.UUID, uuid.UUID]:
    bot = new_bot(owner)
    response = owner.post(
        f"{docs_path(owner, bot)}/sources", {"url": f"{site.base}/", "confirm_authorized": True}
    )
    assert response.status_code == 201, response.text
    org_id, job_id, _ = queue.jobs.pop(0)
    runtime.fetcher = site.fetcher()
    return bot, org_id, job_id


def source_of(owner: Actor, bot: str) -> dict[str, Any]:
    [source] = owner.get(f"{docs_path(owner, bot)}/sources").json()["data"]
    result: dict[str, Any] = source
    return result


@linux
def test_a_hostile_start_page_fails_the_crawl_with_the_parser_code(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, site: Site
) -> None:
    owner = api.signup()
    bot, org_id, job_id = start_crawl(owner, job_queue, runtime, site)
    runtime.parser = hostile("sleep:5", wall_seconds=0.5)

    assert run_crawl_job(runtime, org_id, job_id) == "failed"

    source = source_of(owner, bot)
    assert (source["status"], source["job"]["error_code"]) == ("failed", "parse_timeout")


def test_a_superseded_crawl_attempt_cannot_publish_pages(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, site: Site
) -> None:
    class Supersede(HashingEmbedder):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            api.sql("UPDATE ingestion_jobs SET attempt = attempt + 1 WHERE id = :j", j=job_id)
            return super().embed_documents(texts)

    owner = api.signup()
    bot, org_id, job_id = start_crawl(owner, job_queue, runtime, site)
    runtime.embedder = Supersede()

    assert run_crawl_job(runtime, org_id, job_id) == "stale"

    published = scalar(
        api.owner_engine,
        "SELECT count(*) FROM document_chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.chatbot_id = :b",
        b=bot,
    )
    assert published == 0 and job_row(api, job_id)[0] == "processing"


@pytest.mark.parametrize("through", ["job", "sweeper"])
def test_an_exhausted_crawl_leaves_no_page_stuck_processing(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, site: Site, through: str
) -> None:
    class Down(HashingEmbedder):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            if through == "sweeper":
                raise KeyboardInterrupt  # the worker dies mid-page
            raise TransientIngestionError("embedding_failed", "down")

    owner = api.signup()
    bot, org_id, job_id = start_crawl(owner, job_queue, runtime, site)
    api.sql("UPDATE ingestion_jobs SET max_attempts = 1 WHERE id = :j", j=job_id)
    runtime.embedder = Down()

    with contextlib.suppress(KeyboardInterrupt):
        run_crawl_job(runtime, org_id, job_id)
    if through == "sweeper":
        make_stale(api, job_id)
        sweep_jobs(runtime, job_queue)

    states = rows(api.owner_engine, "SELECT status FROM documents WHERE chatbot_id = :b", b=bot)
    assert states and all(state == "failed" for (state,) in states), states
    assert job_row(api, job_id)[0] == "failed"
    assert source_of(owner, bot)["status"] == "failed"


# ---------------------------------------------------------------- races found in review


def test_the_sweeper_does_not_fail_a_document_that_has_a_newer_job(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listed job finishes and the user reprocesses before the sweeper acts on it."""
    owner = api.signup()
    bot, doc_id, _, old_job = queue_upload(owner, job_queue)
    api.sql(
        "UPDATE ingestion_jobs SET queued_at = now() - interval '2 hours' WHERE id = :j", j=old_job
    )
    original = runtime.tenant_tx
    done: list[bool] = []

    def supersede_then_open(org: uuid.UUID) -> Any:
        if not done and str(org) == owner.org_id:
            done.append(True)
            api.sql("UPDATE ingestion_jobs SET status = 'failed' WHERE id = :j", j=old_job)
            api.sql("UPDATE documents SET status = 'failed' WHERE id = :d", d=doc_id)
            path = f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess"
            assert owner.post(path).status_code == 200
        return original(org)

    monkeypatch.setattr(runtime, "tenant_tx", supersede_then_open, raising=False)

    sweep_jobs(runtime, RecordingJobQueue())

    assert done and get_doc(owner, bot, doc_id)["status"] == "queued"


def test_deleting_a_source_while_its_document_publishes_does_not_deadlock(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_upload(owner, job_queue)
    source_id = scalar(api.owner_engine, "SELECT source_id FROM documents WHERE id = :d", d=doc_id)
    publishing = threading.Event()
    original = pipeline.lock_claim
    calls: list[int] = []

    def slow_lock(session: Any, claim: Any) -> bool:
        owned = original(session, claim)
        calls.append(1)
        if len(calls) == 2:  # the publishing transaction: document and job are now locked
            publishing.set()
            time.sleep(1.5)
        return owned

    monkeypatch.setattr(pipeline, "lock_claim", slow_lock)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(run_document_job, runtime, org_id, job_id)
        assert publishing.wait(10)
        deleted = owner.delete(f"{docs_path(owner, bot)}/sources/{source_id}")
        outcome = running.result(timeout=15)

    assert (deleted.status_code, outcome) == (204, "done"), deleted.text
    assert chunks(api, doc_id) == 0
