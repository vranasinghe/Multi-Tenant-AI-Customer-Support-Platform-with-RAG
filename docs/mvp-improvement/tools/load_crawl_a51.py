"""Bounded background crawling for the mixed chat/crawl capacity series (A5.1).

``perf_a51.py`` copies this next to the real-worker tests as ``test_zz_crawl_load.py``, runs it
in the QA api container while the capacity file runs, and removes it afterwards. Two synthetic
tenants each re-sync a 12-page local website whose pages change every round, through a real
prefork worker (its own database and Redis databases), until ``/tmp/a51-load-stop`` exists or
ten minutes pass.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.rag.storage import S3ObjectStore
from tests.integration.api.conftest import Api
from tests.integration.api.mvp_improvement.test_crawl_worker import (
    FILLER,
    Website,
    crawl_worker,  # noqa: F401 - fixture
    object_store,  # noqa: F401 - fixture
    site,  # noqa: F401 - fixture
    web_fetcher,  # noqa: F401 - fixture
)
from tests.integration.api.mvp_improvement.test_ingestion_worker import (
    Worker,
    broker_settings,  # noqa: F401 - fixture
    job_queue,  # noqa: F401 - fixture
    owner_engine,  # noqa: F401 - fixture
    shared_dir,  # noqa: F401 - fixture
    start_worker,  # noqa: F401 - fixture
    test_database,  # noqa: F401 - fixture
)
from tests.support.site import Site

STOP = Path("/tmp/a51-load-stop")  # noqa: S108
STARTED = Path("/tmp/a51-load-started")  # noqa: S108
PAGES = 12


def publish(web: Site, round_number: int) -> None:
    links = [f"/p{n}" for n in range(1, PAGES)]
    for n in range(PAGES):
        path = "/" if n == 0 else f"/p{n}"
        body = "".join(f"<p>Round {round_number} page {n} part {i}. {FILLER}</p>" for i in range(8))
        web.page(path, f"Page {n}", body, links=links if n == 0 else None)


def test_crawl_load(
    api: Api,
    site: Site,  # noqa: F811
    object_store: S3ObjectStore,  # noqa: F811
    crawl_worker: Callable[..., Worker],  # noqa: F811
) -> None:
    worker = crawl_worker(test_parser="production")
    tenants = [Website(api, site, object_store) for _ in range(2)]
    publish(site, 0)
    jobs: list[tuple[Website, uuid.UUID]] = [(t, t.create()) for t in tenants]
    STARTED.touch()
    started, rounds, finished = time.monotonic(), 0, 0
    outcomes: dict[str, int] = {}
    pages = 0
    while not STOP.exists() and time.monotonic() - started < 600:
        for index, (tenant, job_id) in enumerate(jobs):
            row: Any = tenant.job(job_id)
            if row.status in {"succeeded", "failed"}:
                outcomes[row.status] = outcomes.get(row.status, 0) + 1
                pages += int(row.stats.get("indexed", 0))
                finished += 1
                rounds += 1
                publish(site, rounds)
                jobs[index] = (tenant, tenant.sync())
        time.sleep(0.2)
    report = {
        "seconds": round(time.monotonic() - started, 1),
        "crawls_finished": finished,
        "outcomes": outcomes,
        "pages_indexed": pages,
        "page_failures": sum(
            d.status == "failed" for t in tenants for d in t.documents().values()
        ),
        "worker_errors": worker.log().count('"level": "error"'),
    }
    print("LOAD " + json.dumps(report))
    assert outcomes.get("failed", 0) == 0 and finished > 0, report
