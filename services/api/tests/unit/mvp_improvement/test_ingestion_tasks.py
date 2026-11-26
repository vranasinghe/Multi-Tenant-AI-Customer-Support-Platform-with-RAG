"""AUD-05: task time limits, bounded rescheduling of deferred jobs and fail-closed start-up."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.rag import maintenance, parser_process, pipeline
from app.rag.errors import TransientIngestionError
from app.workers.celery_app import celery_app, create_celery_app
from app.workers.tasks import ingest
from tests.conftest import make_settings

ORG, JOB = str(uuid.uuid4()), str(uuid.uuid4())


# ---------------------------------------------------------------- limits


def test_ingestion_tasks_carry_soft_and_hard_time_limits() -> None:
    celery_app.loader.import_default_modules()
    document = celery_app.tasks["ingest.process_document"]
    crawl = celery_app.tasks["ingest.crawl_source"]

    assert (document.soft_time_limit, document.time_limit) == (120, 180)
    # 200 pages of worst-case fetch, parse and embedding exceed the operator maximum.
    assert (crawl.soft_time_limit, crawl.time_limit) == (3240, 3300)
    assert celery_app.tasks["ingest.sweep"].time_limit is None


def test_the_crawl_budget_follows_page_limits_and_is_capped_by_the_operator() -> None:
    small = make_settings(
        crawl_max_pages_limit=5,
        crawl_delay_seconds=0.5,
        fetch_total_timeout_seconds=20,
        parser_wall_seconds=60,
        embedding_timeout_seconds=30,
    )
    capped = make_settings(crawl_max_task_seconds=600)

    # robots fetch + 5 x (10 s robots crawl-delay cap + 20 s fetch + 60 s parse + 30 s embed)
    assert small.crawl_hard_time_limit_seconds == 20 + 5 * 120
    assert capped.crawl_hard_time_limit_seconds == 600
    assert capped.crawl_soft_time_limit_seconds == 540
    # Longer than a document's budget: a large crawl is never given a document-sized limit.
    assert (
        make_settings().crawl_soft_time_limit_seconds
        > make_settings().ingest_hard_time_limit_seconds
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ingest_soft_time_limit_seconds": 200, "ingest_hard_time_limit_seconds": 180},
        {"crawl_max_task_seconds": 3600},  # must stay below the broker visibility timeout
    ],
)
def test_inconsistent_time_limits_are_refused(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"TIME_LIMIT|crawl_max_task_seconds"):
        make_settings(**overrides)


def test_the_sweep_interval_is_configurable() -> None:
    app = create_celery_app(make_settings(ingest_sweep_interval_seconds=7))

    assert app.conf.beat_schedule["ingest-sweep"]["schedule"] == 7


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_a_deployed_worker_refuses_to_start_without_containment(
    environment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(parser_process, "containment_supported", lambda: False)
    settings = make_settings().model_copy(update={"app_env": environment})

    with pytest.raises(RuntimeError, match="containment"):
        create_celery_app(settings)
    create_celery_app(make_settings())  # local development stays usable, without the guarantee


# ---------------------------------------------------------------- deferral


class Spy:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, outcome: str | Exception) -> None:
        self.outcome = outcome
        self.published: list[dict[str, Any]] = []
        self.deferred: list[bool] = []
        self.woken: list[uuid.UUID] = []
        monkeypatch.setattr(ingest, "get_runtime", lambda: self)
        monkeypatch.setattr(pipeline, "run_document_job", self.run)
        monkeypatch.setattr(maintenance, "defer_job", self.defer)
        monkeypatch.setattr(ingest, "_wake", lambda rt, org: self.woken.append(org))
        monkeypatch.setattr(ingest.process_document, "apply_async", self.publish)
        self.settings = make_settings(ingest_defer_seconds=2)

    def run(self, rt: Any, org_id: uuid.UUID, job_id: uuid.UUID) -> str:
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def defer(self, rt: Any, org_id: uuid.UUID, job_id: uuid.UUID, *, touch: bool) -> None:
        self.deferred.append(touch)

    def publish(self, **options: Any) -> None:
        self.published.append(options)


def test_a_deferred_job_is_rescheduled_instead_of_holding_a_slot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = Spy(monkeypatch, "deferred")

    countdowns = []
    for deferrals in range(5):
        assert ingest.process_document.apply(args=(ORG, JOB), kwargs={"deferrals": deferrals}).get()
        countdowns.append(spy.published[-1]["countdown"])

    assert countdowns == [2, 4, 8, 15, 15]  # grows, then capped
    assert spy.published[-1]["kwargs"] == {"deferrals": 5}
    assert spy.published[-1]["args"] == [ORG, JOB]
    assert spy.deferred == [True] * 5 and spy.woken == []


def test_rescheduling_stops_and_hands_the_job_to_the_sweeper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = Spy(monkeypatch, "deferred")

    result = ingest.process_document.apply(
        args=(ORG, JOB), kwargs={"deferrals": ingest.MAX_DEFERRALS}
    )

    assert result.get() == "deferred"
    assert spy.published == [] and spy.deferred == [False]  # still queued, never failed


@pytest.mark.parametrize("outcome", ["done", "failed", "gone", "stale"])
def test_a_finished_job_wakes_the_organizations_next_one(
    outcome: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spy = Spy(monkeypatch, outcome)

    assert ingest.process_document.apply(args=(ORG, JOB)).get() == outcome

    assert spy.woken == [uuid.UUID(ORG)]


def test_a_skipped_redelivery_wakes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = Spy(monkeypatch, "skipped")

    ingest.process_document.apply(args=(ORG, JOB)).get()

    assert spy.woken == [] and spy.published == []


def test_a_transient_failure_releases_the_permit_and_keeps_celery_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spy = Spy(monkeypatch, TransientIngestionError("storage_error"))
    retried: list[dict[str, Any]] = []

    def retry(**options: Any) -> RuntimeError:
        retried.append(options)
        return RuntimeError("retry requested")

    monkeypatch.setattr(ingest.process_document, "retry", retry)

    result = ingest.process_document.apply(args=(ORG, JOB), kwargs={"deferrals": 3})

    assert result.failed() and spy.woken == [uuid.UUID(ORG)]
    assert retried[0]["args"] == [ORG, JOB] and retried[0]["kwargs"] == {}
