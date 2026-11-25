"""Background-job guarantees: no duplicate processing, bounded retries with backoff, safe retry,
stuck-job recovery, tenant and storage guards in workers, and log hygiene."""

from __future__ import annotations

import contextlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.main import create_app
from app.rag.embeddings import HashingEmbedder
from app.rag.errors import TransientIngestionError
from app.rag.maintenance import sweep_jobs
from app.rag.pipeline import backoff_seconds, run_document_job
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.rag.storage import MemoryObjectStore
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import (
    RETURNS,
    SHIPPING,
    docs_path,
    get_doc,
    new_bot,
    search,
    upload,
)
from tests.support.email import Mailbox
from tests.support.rag import FlakyEmbedder, rows, run_jobs, scalar

pytestmark = pytest.mark.integration

TXT = "text/plain"


def queue_one(
    owner: Actor, job_queue: RecordingJobQueue, data: bytes = SHIPPING.encode()
) -> tuple[str, str, uuid.UUID, uuid.UUID]:
    bot = new_bot(owner)
    response = upload(owner, bot, "doc.txt", data, TXT)
    assert response.status_code == 201, response.text
    org_id, job_id, _ = job_queue.jobs.pop(0)
    return bot, response.json()["id"], org_id, job_id


def chunk_count(api: Api, document_id: str) -> int:
    return int(
        scalar(
            api.owner_engine,
            "SELECT count(*) FROM document_chunks WHERE document_id = :d",
            d=document_id,
        )
    )


# ---------------------------------------------------------------- no duplicate processing


def test_a_redelivered_message_is_skipped_and_creates_no_duplicates(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    _, doc_id, org_id, job_id = queue_one(owner, job_queue)

    outcomes = [run_document_job(runtime, org_id, job_id) for _ in range(3)]

    assert outcomes == ["done", "skipped", "skipped"]
    assert chunk_count(api, doc_id) >= 1
    assert (
        scalar(api.owner_engine, "SELECT attempt FROM ingestion_jobs WHERE id = :j", j=job_id) == 1
    )


def test_concurrent_workers_process_a_job_exactly_once(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    data = (SHIPPING + " " + RETURNS).encode() * 3
    _, doc_id, org_id, job_id = queue_one(owner, job_queue, data)

    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(lambda _: run_document_job(runtime, org_id, job_id), range(6)))

    assert sorted(outcomes) == ["done", "skipped", "skipped", "skipped", "skipped", "skipped"]
    versions = rows(
        api.owner_engine,
        "SELECT DISTINCT document_version FROM document_chunks WHERE document_id = :d",
        d=doc_id,
    )
    assert versions == [(1,)]
    n = chunk_count(api, doc_id)
    assert n == scalar(
        api.owner_engine, "SELECT chunk_count FROM documents WHERE id = :d", d=doc_id
    )


def test_only_one_active_job_can_exist_per_document(api: Api, job_queue: RecordingJobQueue) -> None:
    owner = api.signup()
    bot, doc_id, org_id, _job_id = queue_one(owner, job_queue)

    again = owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess")

    assert again.status_code == 409 and again.json()["code"] == "already_processing"
    with pytest.raises(Exception, match="uq_ingestion_jobs_active_document"):
        api.sql(
            "INSERT INTO ingestion_jobs (id, org_id, chatbot_id, source_id, document_id, kind) "
            "SELECT gen_random_uuid(), org_id, chatbot_id, source_id, id, 'process_document' "
            "FROM documents WHERE id = :d",
            d=doc_id,
        )
    assert org_id == uuid.UUID(owner.org_id)


# ---------------------------------------------------------------------- retries & backoff


def test_backoff_is_exponential_capped_and_jittered() -> None:
    samples = {n: [backoff_seconds(n, 5, 300) for _ in range(50)] for n in (1, 2, 3, 4, 10)}

    for attempt, expected in ((1, 5), (2, 10), (3, 20), (4, 40), (10, 300)):
        assert all(expected * 0.8 - 1 <= v <= expected * 1.2 + 1 for v in samples[attempt]), attempt
    assert len(set(samples[3])) > 1  # jitter
    assert backoff_seconds(5, 0, 300) == 0


def test_transient_embedding_failures_are_retried_until_success_without_duplicates(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    runtime.embedder = FlakyEmbedder(failures=2)

    for expected_attempt in (1, 2):
        with pytest.raises(TransientIngestionError):
            run_document_job(runtime, org_id, job_id)
        doc = get_doc(owner, bot, doc_id)
        assert doc["status"] == "queued" and doc["job"]["status"] == "queued"
        assert (
            doc["job"]["attempt"] == expected_attempt
            and doc["job"]["error_code"] == "embedding_failed"
        )
        assert chunk_count(api, doc_id) == 0
    assert run_document_job(runtime, org_id, job_id) == "done"

    doc = get_doc(owner, bot, doc_id)
    assert (
        doc["status"] == "ready" and doc["job"]["attempt"] == 3 and doc["job"]["error_code"] is None
    )
    assert chunk_count(api, doc_id) == doc["chunk_count"]


def test_retries_stop_at_max_attempts_and_a_manual_retry_then_works(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    runtime.embedder = FlakyEmbedder(failures=10_000)
    max_attempts = runtime.settings.ingest_max_attempts

    results: list[str] = []
    for _ in range(max_attempts):
        try:
            results.append(run_document_job(runtime, org_id, job_id))
        except TransientIngestionError:
            results.append("retry")

    assert results == ["retry"] * (max_attempts - 1) + ["failed"]
    doc = get_doc(owner, bot, doc_id)
    assert doc["status"] == "failed" and doc["error_code"] == "embedding_failed"
    assert doc["job"]["attempt"] == max_attempts and doc["job"]["status"] == "failed"
    assert run_document_job(runtime, org_id, job_id) == "skipped"  # a failed job is never re-run

    runtime.embedder = HashingEmbedder()
    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 200
    run_jobs(runtime, job_queue)
    assert get_doc(owner, bot, doc_id)["status"] == "ready"


def test_permanent_failures_are_not_retried(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    _, doc_id, org_id, job_id = queue_one(owner, job_queue, b"   \n  \n")

    assert run_document_job(runtime, org_id, job_id) == "failed"
    assert (
        scalar(api.owner_engine, "SELECT attempt FROM ingestion_jobs WHERE id = :j", j=job_id) == 1
    )


def test_unexpected_errors_fail_the_job_safely(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)

    def explode(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("secret document text leaked into an exception")

    monkeypatch.setattr("app.rag.pipeline.chunk_blocks", explode)

    assert run_document_job(runtime, org_id, job_id) == "failed"
    doc = get_doc(owner, bot, doc_id)
    assert doc["error_code"] == "internal_error"
    assert "secret" not in str(doc)
    assert "secret" not in str(
        scalar(api.owner_engine, "SELECT error_detail FROM ingestion_jobs WHERE id = :j", j=job_id)
    )


def test_a_failed_reprocess_keeps_serving_the_last_published_version(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot = new_bot(owner)
    response = upload(owner, bot, "a.txt", SHIPPING.encode(), TXT)
    run_jobs(runtime, job_queue)
    doc_id = response.json()["id"]
    before = chunk_count(api, doc_id)
    assert search(owner, bot, "express shipping")

    assert owner.post(f"{docs_path(owner, bot)}/documents/{doc_id}/reprocess").status_code == 200
    org_id, job_id, _ = job_queue.jobs.pop(0)
    runtime.embedder = FlakyEmbedder(failures=10_000)
    for _ in range(runtime.settings.ingest_max_attempts):
        with contextlib.suppress(TransientIngestionError):
            run_document_job(runtime, org_id, job_id)

    doc = get_doc(owner, bot, doc_id)
    assert doc["status"] == "failed" and doc["version"] == 1
    assert chunk_count(api, doc_id) == before
    assert search(owner, bot, "express shipping")  # old content still answers


# --------------------------------------------------------------------- sweeper


def age_job(api: Api, job_id: uuid.UUID, *, status: str, minutes: int = 120) -> None:
    api.sql(
        "UPDATE ingestion_jobs SET status = :s, queued_at = now() - make_interval(mins => :m), "
        "heartbeat_at = now() - make_interval(mins => :m), started_at = now() - make_interval(mins => :m) "
        "WHERE id = :j",
        s=status,
        m=minutes,
        j=job_id,
    )


def test_sweeper_requeues_jobs_stuck_in_processing_and_they_then_complete(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    api.sql("UPDATE ingestion_jobs SET attempt = 1 WHERE id = :j", j=job_id)
    age_job(api, job_id, status="processing")  # the worker died mid-job

    requeued = sweep_jobs(runtime, job_queue)

    assert requeued == 1
    assert job_queue.jobs == [(org_id, job_id, "process_document")]
    assert run_jobs(runtime, job_queue) == ["done"]
    assert get_doc(owner, bot, doc_id)["status"] == "ready"
    assert chunk_count(api, doc_id) == get_doc(owner, bot, doc_id)["chunk_count"]


def test_sweeper_republishes_jobs_whose_message_was_lost(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    assert sweep_jobs(runtime, job_queue) == 0  # fresh queued jobs are left alone
    age_job(api, job_id, status="queued", minutes=10)

    assert sweep_jobs(runtime, job_queue) == 1
    assert run_jobs(runtime, job_queue) == ["done"]


def test_sweeper_fails_jobs_that_keep_dying_instead_of_looping_forever(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, _org_id, job_id = queue_one(owner, job_queue)
    api.sql("UPDATE ingestion_jobs SET attempt = max_attempts WHERE id = :j", j=job_id)
    age_job(api, job_id, status="processing")

    assert sweep_jobs(runtime, job_queue) == 0

    doc = get_doc(owner, bot, doc_id)
    assert doc["status"] == "failed" and doc["job"]["status"] == "failed"
    assert job_queue.jobs == []


def test_sweeper_discovery_does_not_expose_other_tables_to_the_runtime_role(
    api: Api, app_engine: Any
) -> None:
    from sqlalchemy import text

    with app_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM ingestion_jobs")).scalar_one() == 0  # RLS
        listed = conn.execute(text("SELECT * FROM app.list_stuck_jobs(now(), now())")).all()
        assert all(len(row) == 4 for row in listed)  # ids and status only, never content


# ---------------------------------------------------------- worker-side tenant guards


def test_a_job_cannot_be_claimed_under_another_organization(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner, other = api.signup(), api.signup()
    _, doc_id, org_id, job_id = queue_one(owner, job_queue)

    assert run_document_job(runtime, uuid.UUID(other.org_id), job_id) == "skipped"
    assert (
        scalar(api.owner_engine, "SELECT status FROM ingestion_jobs WHERE id = :j", j=job_id)
        == "queued"
    )
    assert chunk_count(api, doc_id) == 0
    assert run_document_job(runtime, org_id, job_id) == "done"


def test_workers_refuse_storage_keys_outside_their_organization(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner, victim = api.signup(), api.signup()
    victim_bot = new_bot(victim)
    upload(victim, victim_bot, "private.txt", b"the victim's confidential text here", TXT)
    [victim_key] = object_store.keys()
    job_queue.jobs.clear()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    api.sql("UPDATE documents SET storage_key = :k WHERE id = :d", k=victim_key, d=doc_id)
    reads: list[str] = []
    original_get = object_store.get
    object_store.get = lambda key, **kw: (reads.append(key), original_get(key, **kw))[1]  # type: ignore[method-assign,func-returns-value]

    assert run_document_job(runtime, org_id, job_id) == "failed"

    assert get_doc(owner, bot, doc_id)["error_code"] == "storage_error"
    assert victim_key not in reads
    assert search(owner, bot, "confidential") == []


def test_tampered_originals_are_detected_by_hash(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    [key] = object_store.keys()
    object_store.put(key, b"completely different content now", content_type=TXT)

    assert run_document_job(runtime, org_id, job_id) == "failed"
    assert get_doc(owner, bot, doc_id)["error_code"] == "corrupt"


def test_storage_hiccup_is_retried_not_failed(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, object_store: MemoryObjectStore
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)
    object_store.fail_next_get = 1

    with pytest.raises(TransientIngestionError):
        run_document_job(runtime, org_id, job_id)
    assert get_doc(owner, bot, doc_id)["status"] == "queued"
    assert run_document_job(runtime, org_id, job_id) == "done"


def test_deleting_a_document_mid_processing_leaves_no_orphans(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    owner = api.signup()
    bot, doc_id, org_id, job_id = queue_one(owner, job_queue)

    class DeletingEmbedder(HashingEmbedder):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            assert owner.delete(f"{docs_path(owner, bot)}/documents/{doc_id}").status_code == 204
            return super().embed_documents(texts)

    runtime.embedder = DeletingEmbedder()

    assert run_document_job(runtime, org_id, job_id) == "gone"
    assert chunk_count(api, doc_id) == 0
    assert scalar(api.owner_engine, "SELECT count(*) FROM documents WHERE id = :d", d=doc_id) == 0


# ------------------------------------------------------------------- log hygiene


def test_logs_never_contain_document_text_filenames_or_urls(
    api_settings: Settings,
    mailbox: Mailbox,
    owner_engine: Engine,
    runtime: Runtime,
    object_store: MemoryObjectStore,
    job_queue: RecordingJobQueue,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = api_settings.model_copy(update={"log_level": "DEBUG", "log_format": "json"})
    secret = "PROJECT-NIGHTINGALE-ACQUISITION-PRICE-41M"
    app = create_app(settings, email_sender=mailbox, object_store=object_store, job_queue=job_queue)
    with TestClient(app, base_url="https://testserver") as client:
        api = Api(client=client, mailbox=mailbox, owner_engine=owner_engine)
        owner = api.signup()
        bot = new_bot(owner)
        upload(owner, bot, "confidential-merger-plan.txt", f"{secret} is secret.".encode(), TXT)
        run_jobs(runtime, job_queue)
        upload(owner, bot, "scan.pdf", b"%PDF-1.4 garbage " + secret.encode(), "application/pdf")
        run_jobs(runtime, job_queue)
        search(owner, bot, secret)

    output = capsys.readouterr()
    logs = (output.out + output.err).lower()
    assert "ingest." in logs, "expected ingestion to log something"
    for needle in (secret.lower(), "nightingale", "confidential-merger-plan", "scan.pdf"):
        assert needle not in logs, needle
