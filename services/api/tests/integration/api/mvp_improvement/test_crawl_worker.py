"""AUD05-CRAWL: website crawls through a real, disposable Celery prefork worker.

Real queue, real tasks, real parser children, real object storage, a private database and Redis
databases 13/12. The website is a loopback server that only ``site.test`` resolves to.

Test-only timings (runtime defaults in brackets): stuck 30 s (900), sweep 5 s (120). The crawl
time budget is derived from settings, so the limit tests shrink its inputs:

==============================  ======  ======  =======
setting                         soft    hard    default
==============================  ======  ======  =======
CRAWL_MAX_PAGES_LIMIT           1       1       200
FETCH_TOTAL_TIMEOUT_SECONDS     1       1       20
EMBEDDING_TIMEOUT_SECONDS       1       1       30
PARSER_WALL_SECONDS             20      6       60
derived crawl hard / soft (s)   33/16   19/9    3300/3240
==============================  ======  ======  =======
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.rag.queue import CeleryJobQueue
from app.rag.safe_fetch import SafeFetcher
from app.rag.storage import ObjectNotFoundError, S3ObjectStore
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.mvp_improvement.test_ingestion_worker import (
    RECOVERY_BOUND,
    Worker,
    alive,
    broker_settings,  # noqa: F401 - fixture
    evidence,
    is_ready,
    job,
    job_queue,  # noqa: F401 - fixture
    owner_engine,  # noqa: F401 - fixture
    parsers,
    send,
    shared_dir,  # noqa: F401 - fixture
    start_worker,  # noqa: F401 - fixture
    test_database,  # noqa: F401 - fixture
    wait_for,
)
from tests.integration.api.test_knowledge_documents import docs_path, new_bot, search
from tests.support.rag import rows, scalar
from tests.support.site import Site, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        __import__("sys").platform != "linux", reason="real prefork workers need Linux"
    ),
]

FILLER = "Standard shipping takes three to five business days after the order is dispatched. " * 4
TENANT_B = "Express shipping takes one to two business days and costs extra at checkout."
SOFT = {
    "crawl_max_pages_limit": 1,
    "fetch_total_timeout_seconds": 1,
    "embedding_timeout_seconds": 1,
    "parser_wall_seconds": 20,
}
HARD = {**SOFT, "parser_wall_seconds": 6}


@pytest.fixture
def object_store(api_settings: Settings) -> S3ObjectStore:
    if not __import__("os").environ.get("S3_ENDPOINT_URL"):
        pytest.skip("S3_ENDPOINT_URL is required: these tests use real object storage")
    return S3ObjectStore(api_settings)


@pytest.fixture
def site() -> Iterator[Site]:
    with serve() as s:
        s.text("/robots.txt", "User-agent: *\n")
        yield s


@pytest.fixture
def web_fetcher(site: Site) -> SafeFetcher:
    return site.fetcher()


@pytest.fixture
def crawl_worker(
    start_worker: Callable[..., Worker],  # noqa: F811 - the imported fixture
    site: Site,
) -> Callable[..., Worker]:
    def start(**settings: Any) -> Worker:
        return start_worker(
            test_site_port=site.port, test_object_store="s3", crawl_delay_seconds=0, **settings
        )

    return start


def page(
    site: Site, path: str, marker: str, *, extra: str = "", links: list[str] | None = None
) -> None:
    site.page(path, f"Page {path}", f"<p>{marker}. {FILLER}</p>{extra}", links=links)


class Website:
    """A website source created through the API, and what became of it."""

    def __init__(self, api: Api, site: Site, store: S3ObjectStore) -> None:
        self.api, self.site, self.store = api, site, store
        self.owner: Actor = api.signup()
        self.bot = new_bot(self.owner)

    def create(self, **body: Any) -> uuid.UUID:
        response = self.owner.post(
            f"{docs_path(self.owner, self.bot)}/sources",
            {"url": f"{self.site.base}/", "confirm_authorized": True, **body},
        )
        assert response.status_code == 201, response.text
        self.source_id = scalar(
            self.api.owner_engine,
            "SELECT id FROM knowledge_sources WHERE chatbot_id = :b",
            b=self.bot,
        )
        return self.latest_job_id()

    def latest_job_id(self) -> uuid.UUID:
        job_id: uuid.UUID = scalar(
            self.api.owner_engine,
            "SELECT id FROM ingestion_jobs WHERE source_id = :s AND kind = 'crawl' "
            "ORDER BY id DESC LIMIT 1",
            s=self.source_id,
        )
        return job_id

    def sync(self) -> uuid.UUID:
        response = self.owner.post(
            f"{docs_path(self.owner, self.bot)}/sources/{self.source_id}/sync"
        )
        assert response.status_code < 300, response.text
        return self.latest_job_id()

    def job(self, job_id: uuid.UUID) -> Any:
        [row] = rows(
            self.api.owner_engine,
            "SELECT status, attempt, error_code, stats, "
            "extract(epoch FROM finished_at - started_at) AS processed "
            "FROM ingestion_jobs WHERE id = :j",
            j=job_id,
        )
        return row

    def finished(self, job_id: uuid.UUID, timeout: float) -> Any:
        wait_for(
            lambda: self.job(job_id).status in {"succeeded", "failed"},
            timeout,
            "the crawl to finish",
        )
        return self.job(job_id)

    def documents(self) -> dict[str, Any]:
        return {
            row.uri.removeprefix(self.site.base): row
            for row in rows(
                self.api.owner_engine,
                "SELECT id, uri, status, version, storage_key, chunk_count FROM documents "
                "WHERE source_id = :s",
                s=self.source_id,
            )
        }

    def chunks(self, document_id: uuid.UUID) -> list[Any]:
        return rows(
            self.api.owner_engine,
            "SELECT document_version, content, vector_dims(embedding) AS dims, embedding_model "
            "FROM document_chunks WHERE document_id = :d ORDER BY ordinal",
            d=document_id,
        )

    def published(self, document_id: uuid.UUID) -> str:
        return " ".join(c.content for c in self.chunks(document_id))

    def original(self, key: str) -> str | None:
        try:
            return self.store.get(key, max_bytes=1_000_000).decode()
        except ObjectNotFoundError:
            return None

    def pending(self) -> list[Any]:
        return rows(
            self.api.owner_engine,
            "SELECT storage_key, extract(epoch FROM created_at - now()) AS due_in "
            "FROM storage_deletions WHERE org_id = :o",
            o=self.owner.org_id,
        )

    def let_grace_pass(self) -> None:
        self.api.sql(
            "UPDATE storage_deletions SET created_at = now() WHERE org_id = :o",
            o=self.owner.org_id,
        )

    def intact(self, document: Any, marker: str) -> None:
        """The document still serves what it published before, from the original it published."""
        now = self.documents()["/"]
        assert (now.version, now.storage_key) == (document.version, document.storage_key)
        assert marker in self.published(now.id) and marker in (self.original(now.storage_key) or "")
        assert search(self.owner, self.bot, "standard shipping")


@pytest.fixture
def website(api: Api, site: Site, object_store: S3ObjectStore) -> Website:
    return Website(api, site, object_store)


def effective_limits(queue: CeleryJobQueue) -> dict[str, str]:
    """The task limits as the running worker reports them."""
    inspect = queue._celery.control.inspect(timeout=5)
    replies = inspect.registered("soft_time_limit", "time_limit") or {}
    return {
        line.split(" ", 1)[0]: line.split(" ", 1)[1]
        for lines in replies.values()
        for line in lines
        if line.startswith("ingest.") and " " in line
    }


def published_first(website: Website, crawl_worker: Callable[..., Worker], **settings: Any) -> Any:
    """Version one of a one-page site, then the same worker for what follows."""
    worker = crawl_worker(**settings)
    page(website.site, "/", "zeromarker")
    first = website.create(max_pages=1)
    assert website.finished(first, 30).status == "succeeded"
    return worker, website.documents()["/"]


# ---------------------------------------------------------------- success


def test_a_whole_website_is_crawled_and_published_by_a_real_worker(
    website: Website,
    crawl_worker: Callable[..., Worker],
    job_queue: CeleryJobQueue,  # noqa: F811
) -> None:
    worker = crawl_worker(test_parser="production")
    page(website.site, "/", "homemarker", links=["/ship", "/returns"])
    page(website.site, "/ship", "shipmarker")
    page(website.site, "/returns", "returnmarker")

    job_id = website.create()
    done = website.finished(job_id, 60)

    assert (done.status, done.attempt, done.stats["errors"]) == ("succeeded", 1, 0)
    documents = website.documents()
    assert set(documents) == {"/", "/ship", "/returns"}
    for path, marker in (
        ("/", "homemarker"),
        ("/ship", "shipmarker"),
        ("/returns", "returnmarker"),
    ):
        document = documents[path]
        chunks = website.chunks(document.id)
        assert (document.status, document.version) == ("ready", 1)
        assert len(chunks) == document.chunk_count >= 1
        assert {(c.document_version, c.dims) for c in chunks} == {(1, 1536)}
        assert marker in website.published(document.id)
        assert marker in (website.original(document.storage_key) or "")
    assert search(website.owner, website.bot, "standard shipping")
    assert website.pending() == [] and parsers() == {}
    parsed = worker.log().count('"parser.finished"')
    assert parsed == 3
    limits = effective_limits(job_queue)
    assert limits["ingest.crawl_source"] == "[soft_time_limit=3240 time_limit=3300]", limits
    evidence(
        "crawl-success",
        {
            "pages": len(documents),
            "parser_children": parsed,
            "vector_dimensions": 1536,
            "job_seconds": done.processed,
            "effective_limits": limits,
        },
    )


def test_bad_pages_are_counted_and_skipped_under_the_real_limits(
    website: Website, crawl_worker: Callable[..., Worker]
) -> None:
    crawl_worker(parser_wall_seconds=4, parser_memory_bytes=256 * 1024**2, fetch_max_bytes=100_000)
    bad = ["/hang", "/memory", "/garbled", "/huge", "/metadata", "/private", "/other-loopback"]
    page(website.site, "/", "homemarker", links=[*bad, "/fine"])
    page(website.site, "/fine", "finemarker")
    page(website.site, "/hang", "hangmarker", extra="<!--HOSTILE:sleep:60-->")
    page(website.site, "/memory", "memorymarker", extra="<!--HOSTILE:allocate-->")
    page(website.site, "/garbled", "garbledmarker", extra="<!--HOSTILE:malformed:not-json-->")
    page(website.site, "/huge", "hugemarker", extra="<p>padding words </p>" * 8000)
    port = website.site.port
    website.site.redirect("/metadata", f"http://169.254.169.254:{port}/latest/meta-data")
    website.site.redirect("/private", f"http://10.255.255.1:{port}/internal")
    website.site.redirect("/other-loopback", f"http://127.0.0.2:{port}/admin")

    done = website.finished(website.create(), 60)

    assert done.status == "succeeded", done
    assert set(website.documents()) == {"/", "/fine"}
    stats = done.stats
    assert (stats["errors"], stats["blocked"]) == (4, 3), stats
    codes = " ".join(stats["error_samples"])
    assert parsers() == {}
    for code in ("parse_timeout", "parse_resource_limit", "parse_invalid_output", "too_large"):
        assert code in codes, stats
    evidence("crawl-bad-pages", {"stats": stats})


# ---------------------------------------------------------------- crawl time limits


def test_the_crawl_soft_limit_ends_the_parser_and_keeps_published_content(
    website: Website,
    crawl_worker: Callable[..., Worker],
    job_queue: CeleryJobQueue,  # noqa: F811
    api_settings: Settings,
) -> None:
    api_settings.ingest_max_attempts = 1
    worker, before = published_first(website, crawl_worker, **SOFT)
    limits = effective_limits(job_queue)
    assert limits["ingest.crawl_source"] == "[soft_time_limit=16 time_limit=33]", limits

    page(website.site, "/", "alphamarker", extra="<!--HOSTILE:sleep:60-->")
    job_id = website.sync()
    [parser] = wait_for(lambda: list(parsers()), 15, "the hung parser")
    started = time.monotonic()
    done = website.finished(job_id, 30)
    elapsed = time.monotonic() - started

    assert (done.status, done.error_code) == ("failed", "task_timeout"), done
    assert "Soft time limit (16s) exceeded" in worker.log()
    assert not alive(parser) and parsers() == {}
    website.intact(before, "zeromarker")
    evidence(
        "crawl-soft-limit",
        {
            "effective_limits": limits,
            "parser_pid": parser,
            "seconds_from_parser_seen_to_failed": elapsed,
            "job_seconds": done.processed,
        },
    )


def test_the_crawl_hard_limit_kills_the_task_and_the_sweeper_recovers(
    website: Website,
    crawl_worker: Callable[..., Worker],
    job_queue: CeleryJobQueue,  # noqa: F811
    api_settings: Settings,
) -> None:
    api_settings.ingest_max_attempts = 1
    worker, before = published_first(website, crawl_worker, **HARD)
    limits = effective_limits(job_queue)
    assert limits["ingest.crawl_source"] == "[soft_time_limit=9 time_limit=19]", limits

    page(website.site, "/", "alphamarker HOSTILE-IGNORE-SOFT-LIMIT")
    job_id = website.sync()
    # The upload is on record, and protected, while its task is still running.
    [staged] = wait_for(website.pending, 15, "the staged upload")
    assert staged.due_in > 200
    wait_for(lambda: website.original(staged.storage_key), 10, "the uploaded object")
    wait_for(lambda: "Hard time limit (19s) exceeded" in worker.log(), 40, "the hard limit")
    killed = time.monotonic()
    assert website.job(job_id).status == "processing"  # nothing ran in the killed process
    done = website.finished(job_id, RECOVERY_BOUND)
    recovery = time.monotonic() - killed

    assert recovery <= RECOVERY_BOUND
    assert (done.status, done.error_code, done.attempt) == ("failed", "internal_error", 1)
    assert website.documents()["/"].status == "failed"  # nothing stays "processing"
    assert parsers() == {}
    website.intact(before, "zeromarker")

    # The pool sends SIGTERM and then, 100 ms later, SIGKILL: the dying process may or may not
    # release its upload. Either way the periodic purge removes it, at the latest once it is due.
    released = not any(row.due_in > 0 for row in website.pending())
    website.let_grace_pass()
    wait_for(lambda: website.pending() == [], 20, "the periodic purge")
    assert website.original(staged.storage_key) is None
    website.intact(before, "zeromarker")
    evidence(
        "crawl-hard-limit",
        {
            "effective_limits": limits,
            "recovery_seconds": recovery,
            "bound_seconds": RECOVERY_BOUND,
            "staged_object_reclaim_delay_seconds": staged.due_in,
            "released_by_the_terminated_process": released,
        },
    )


# ---------------------------------------------------------------- worker loss and restart


def test_a_restarted_worker_finishes_a_crawl_without_duplicating_pages(
    website: Website,
    crawl_worker: Callable[..., Worker],
    shared_dir: Path,  # noqa: F811
) -> None:
    first = crawl_worker()
    page(website.site, "/", "homemarker", links=["/second"])
    marker = shared_dir / "calls"
    page(website.site, "/second", "secondmarker", extra=f"<!--HOSTILE:hang-on-call:1:{marker}-->")
    job_id = website.create()
    wait_for((shared_dir / "calls.1").exists, 30, "the second page's parse")
    [parser] = parsers()
    home = website.documents()["/"]
    assert home.status == "ready"

    first.kill()
    killed = time.monotonic()
    wait_for(lambda: not alive(parser), 2, "the orphaned parser to die")
    crawl_worker()
    done = website.finished(job_id, RECOVERY_BOUND + 10)
    recovery = time.monotonic() - killed

    assert recovery <= RECOVERY_BOUND
    assert (done.status, done.attempt) == ("succeeded", 2), done
    documents = website.documents()
    assert set(documents) == {"/", "/second"}
    assert documents["/"] == home  # unchanged page: not re-uploaded, not re-published
    for document in documents.values():
        chunks = website.chunks(document.id)
        assert document.version == 1 and len(chunks) == document.chunk_count
    assert parsers() == {} and website.pending() == []
    evidence(
        "crawl-worker-restart", {"recovery_seconds": recovery, "bound_seconds": RECOVERY_BOUND}
    )


@pytest.mark.parametrize("moment", ["STOREHANGBEFORE", "STOREHANGAFTER"])
def test_losing_a_worker_around_an_upload_leaves_the_published_original(
    website: Website,
    crawl_worker: Callable[..., Worker],
    shared_dir: Path,  # noqa: F811
    moment: str,
) -> None:
    first, before = published_first(website, crawl_worker)
    page(website.site, "/", f"alphamarker {moment}")
    job_id = website.sync()
    wait_for((shared_dir / "store.held").exists, 20, "the upload")
    time.sleep(0.5)

    first.kill()
    killed = time.monotonic()

    website.intact(before, "zeromarker")
    [abandoned] = website.pending()
    uploaded = website.original(abandoned.storage_key)
    assert (uploaded is not None) == (moment == "STOREHANGAFTER")
    crawl_worker()
    done = website.finished(job_id, RECOVERY_BOUND + 10)
    recovery = time.monotonic() - killed

    assert recovery <= RECOVERY_BOUND
    assert (done.status, done.attempt) == ("succeeded", 2), done
    now = website.documents()["/"]
    assert now.version == 2 and now.storage_key not in {before.storage_key, abandoned.storage_key}
    assert "alphamarker" in website.published(now.id)
    assert "alphamarker" in (website.original(now.storage_key) or "")
    website.let_grace_pass()
    wait_for(lambda: website.pending() == [], 20, "the periodic purge")
    assert website.original(abandoned.storage_key) is None
    assert website.original(before.storage_key) is None
    assert website.original(now.storage_key)
    evidence(
        f"crawl-loss-{moment.lower()}",
        {"recovery_seconds": recovery, "object_existed_at_loss": uploaded is not None},
    )


# ---------------------------------------------------------------- deletion, duplicates, fencing


def test_deleting_a_source_stops_its_crawl_and_removes_its_objects(
    website: Website, crawl_worker: Callable[..., Worker]
) -> None:
    _, before = published_first(website, crawl_worker)
    page(website.site, "/", "alphamarker", extra="<!--HOSTILE:sleep:60-->")
    website.sync()
    [parser] = wait_for(lambda: list(parsers()), 15, "the hung parser")

    path = f"{docs_path(website.owner, website.bot)}/sources/{website.source_id}"
    started = time.monotonic()
    assert website.owner.delete(path).status_code == 204
    wait_for(lambda: not alive(parser), 5, "the parser to be cancelled")
    cancelled = time.monotonic() - started

    wait_for(lambda: website.pending() == [], 20, "the periodic purge")
    assert website.original(before.storage_key) is None
    for table in ("documents", "ingestion_jobs"):
        assert (
            scalar(
                website.api.owner_engine,
                f"SELECT count(*) FROM {table} WHERE source_id = :s",  # noqa: S608
                s=website.source_id,
            )
            == 0
        )
    evidence("crawl-source-deleted", {"parser_cancelled_after_seconds": cancelled})


def test_duplicate_crawl_deliveries_publish_once(
    website: Website,
    crawl_worker: Callable[..., Worker],
    job_queue: CeleryJobQueue,  # noqa: F811
) -> None:
    worker = crawl_worker()
    page(website.site, "/", "homemarker", links=["/ship"])
    page(website.site, "/ship", "shipmarker")
    job_id = website.create()
    org = uuid.UUID(website.owner.org_id)
    for _ in range(3):
        job_queue.enqueue(org_id=org, job_id=job_id, kind="crawl")

    wait_for(lambda: worker.log().count("succeeded in") >= 4, 40, "all four deliveries")

    done = website.finished(job_id, 10)
    assert (done.status, done.attempt) == ("succeeded", 1)
    documents = website.documents()
    assert set(documents) == {"/", "/ship"}
    for document in documents.values():
        assert document.version == 1
        assert len(website.chunks(document.id)) == document.chunk_count
    assert website.pending() == []


def test_a_superseded_crawl_attempt_cannot_change_a_page(
    website: Website,
    crawl_worker: Callable[..., Worker],
    shared_dir: Path,  # noqa: F811
) -> None:
    worker, _ = published_first(website, crawl_worker)
    page(website.site, "/", "alphamarker HOLDEMBED")
    job_id = website.sync()
    wait_for((shared_dir / "embed.held").exists, 20, "attempt one to stall")
    page(website.site, "/", "bravomarker")

    done = website.finished(job_id, RECOVERY_BOUND + 10)  # the sweeper hands it to attempt two
    assert (done.status, done.attempt) == ("succeeded", 2), done
    published = website.documents()["/"]
    (shared_dir / "embed.release").touch()
    wait_for(lambda: '"ingest.attempt_abandoned"' in worker.log(), 20, "attempt one to give up")

    assert website.documents()["/"] == published and published.version == 2
    assert "bravomarker" in website.published(published.id)
    assert "alphamarker" not in website.published(published.id)
    assert "bravomarker" in (website.original(published.storage_key) or "")
    wait_for(lambda: website.pending() == [], 20, "both old objects to be purged")
    evidence("crawl-superseded", {"attempts": done.attempt, "version": published.version})


def test_crawl_retries_are_bounded_and_keep_published_content(
    website: Website, crawl_worker: Callable[..., Worker], api_settings: Settings
) -> None:
    api_settings.ingest_max_attempts = 2
    _, before = published_first(website, crawl_worker)
    page(website.site, "/", "alphamarker FAILEMBED")
    job_id = website.sync()

    done = website.finished(job_id, 60)

    assert (done.status, done.attempt, done.error_code) == ("failed", 2, "embedding_failed"), done
    assert website.documents()["/"].status == "failed"
    website.intact(before, "zeromarker")
    wait_for(lambda: website.pending() == [], 20, "the failed uploads to be purged")
    time.sleep(2)
    assert website.job(job_id).attempt == 2
    evidence("crawl-retry-exhaustion", {"attempts": done.attempt})


# ---------------------------------------------------------------- another tenant


def test_another_tenant_ingests_while_a_crawl_is_stuck(
    website: Website, crawl_worker: Callable[..., Worker], api: Api
) -> None:
    crawl_worker(parser_wall_seconds=12)
    page(website.site, "/", "alphamarker", extra="<!--HOSTILE:sleep:60-->")
    other = api.signup()
    other_bot = new_bot(other)
    warm = send(other, other_bot, f"warm up {uuid.uuid4()}")
    wait_for(lambda: is_ready(api, warm), 20, "warm-up")
    job_id = website.create()
    wait_for(lambda: list(parsers()), 20, "the stuck crawl")
    waiting = send(website.owner, website.bot, f"Tenant A's document. {TENANT_B}")

    submitted = time.monotonic()
    normal = send(other, other_bot, f"Tenant B's document. {TENANT_B}")
    wait_for(lambda: is_ready(api, normal), 5, "tenant B to be ready")
    ready = time.monotonic() - submitted

    assert job(api, normal)["waited"] <= 2 and ready <= 5
    assert website.job(job_id).status == "processing"
    held = job(api, waiting)
    assert (held["status"], held["attempt"]) == ("queued", 0)
    assert website.finished(job_id, 30).error_code == "parse_timeout"
    wait_for(lambda: is_ready(api, waiting), 15, "tenant A's document afterwards")
    assert is_ready(api, normal) and search(other, other_bot, "express shipping")
    evidence(
        "crawl-fairness",
        {
            "tenant_b_queue_wait_seconds": job(api, normal)["waited"],
            "tenant_b_ready_seconds": ready,
        },
    )
