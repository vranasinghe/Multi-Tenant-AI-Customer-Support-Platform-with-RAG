"""AUD-06 inbox performance fixture: 10,000 conversations, 20 warmed reads per query.

A pytest module kept outside the tree: it is copied to
``services/api/tests/integration/api/mvp_improvement/test_zz_perf_inbox.py``, run once in the QA
api container with ``AUDIT_OUTPUT_DIR`` set, and removed. Its own database.

Tenant A holds 7,000 conversations over two chatbots, B 2,000 and C 1,000; each has six messages.
One further conversation of A has 2,000 messages.
"""

from __future__ import annotations

import json
import os
import platform
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, event, text

from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_knowledge_documents import new_bot
from tests.support.database import TestDatabase, temporary_database

pytestmark = pytest.mark.integration

LIMIT_MS = 300
READS = 20


@pytest.fixture(scope="module")
def test_database() -> Iterator[TestDatabase]:
    with temporary_database() as database:
        yield database


@pytest.fixture(scope="module")
def owner_engine(test_database: TestDatabase) -> Iterator[Engine]:
    engine = create_engine(test_database.owner_url)
    yield engine
    engine.dispose()


def seed(api: Api, actor: Actor, bots: list[str], total: int) -> None:
    per_bot = total // len(bots)
    for offset, bot in enumerate(bots):
        api.sql(
            "INSERT INTO conversations (id, org_id, chatbot_id, channel, status, preview, "
            "created_at, last_message_at) SELECT gen_random_uuid(), :o, :b, "
            "CASE WHEN n % 3 = 0 THEN 'playground' ELSE 'widget' END, "
            "CASE WHEN n % 10 = 0 THEN 'resolved' ELSE 'open' END, "
            "'How do I return order number ' || n || '?', "
            "now() - ((n * 7 + :f) || ' seconds')::interval - interval '1 hour', "
            "now() - ((n * 7 + :f) || ' seconds')::interval "
            "FROM generate_series(1, :n) AS n",
            o=actor.org_id,
            b=bot,
            n=per_bot,
            f=offset,
        )


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, round(fraction * len(ordered)) - 1)]


def test_inbox_reads_stay_within_the_local_target(api: Api, owner_engine: Engine) -> None:
    a, b, c = api.signup(), api.signup(), api.signup()
    bots_a = [new_bot(a), new_bot(a)]
    seed(api, a, bots_a, 7000)
    seed(api, b, [new_bot(b)], 2000)
    seed(api, c, [new_bot(c)], 1000)
    api.sql(
        "INSERT INTO messages (id, org_id, conversation_id, role, content, status, citations, "
        "created_at) SELECT gen_random_uuid(), c.org_id, c.id, "
        "CASE WHEN n % 2 = 1 THEN 'user' ELSE 'assistant' END, "
        "'Message ' || n || ' about returns, shipping and invoices for ' || c.preview, 'complete', "
        "'[]'::jsonb, c.created_at + (n || ' seconds')::interval "
        "FROM conversations c CROSS JOIN generate_series(1, 6) AS n"
    )
    [long_id] = api.sql(
        "SELECT id FROM conversations WHERE org_id = :o ORDER BY last_message_at DESC LIMIT 1",
        o=a.org_id,
    )[0]
    api.sql(
        "INSERT INTO messages (id, org_id, conversation_id, role, content, status, created_at) "
        "SELECT gen_random_uuid(), :o, :c, 'user', repeat('A long transcript line. ', 12), "
        "'complete', timestamptz '2026-01-01' + (n || ' seconds')::interval "
        "FROM generate_series(1, 1994) AS n",
        o=a.org_id,
        c=long_id,
    )
    with owner_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql("VACUUM ANALYZE")

    base = f"/orgs/{a.org_id}/conversations"
    deep = a.get(f"{base}?limit=100").json()["next_cursor"]
    for _ in range(20):  # a position 2,000 rows down
        deep = a.get(f"{base}?limit=100&cursor={deep}").json()["next_cursor"]
    older = a.get(f"{base}/{long_id}").json()["older_cursor"]
    cases = {
        "list, first page of 25": f"{base}?limit=25",
        "list, first page of 100": f"{base}?limit=100",
        "list, page after 2,100 rows": f"{base}?limit=100&cursor={deep}",
        "list, one chatbot": f"{base}?limit=25&chatbot_id={bots_a[1]}",
        "list, widget channel": f"{base}?limit=25&channel=widget",
        "list, resolved": f"{base}?limit=25&status=resolved",
        "list, message search": f"{base}?limit=25&q=invoices",
        "transcript, newest 200 of 2,000": f"{base}/{long_id}",
        "messages, older page of 50": f"{base}/{long_id}/messages?limit=50&cursor={older}",
    }

    statements: list[tuple[str, Any]] = []

    def record(_c: Any, _cur: Any, statement: str, parameters: Any, *_r: Any) -> None:
        statements.append((statement, parameters))

    results: dict[str, Any] = {}
    plans: dict[str, str] = {}
    app_engine = create_engine(
        api.owner_engine.url.set(
            username=os.environ["DATABASE_URL"].split("//")[1].split(":")[0],
            password=os.environ["DATABASE_URL"].split("//")[1].split(":")[1].split("@")[0],
        )
    )
    for name, path in cases.items():
        for _ in range(3):
            assert a.get(path).status_code == 200, name
        timings: list[float] = []
        for _ in range(READS):
            started = time.perf_counter()
            response = a.get(path)
            timings.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200
        statements.clear()
        event.listen(Engine, "before_cursor_execute", record)
        response = a.get(path)
        event.remove(Engine, "before_cursor_execute", record)
        body = response.json()
        results[name] = {
            "p50_ms": round(percentile(timings, 0.5), 1),
            "p95_ms": round(percentile(timings, 0.95), 1),
            "max_ms": round(max(timings), 1),
            "statements": len(statements),
            "payload_bytes": len(response.content),
            "rows": len(body.get("data", body.get("messages", []))),
        }
        # Plans as the unprivileged runtime role, so row-level security is part of them.
        chosen = [
            (s, p)
            for s, p in statements
            if s.lstrip().upper().startswith("SELECT")
            and ("FROM conversations" in s or "FROM messages" in s)
        ]
        text_plans = []
        with app_engine.connect() as connection:
            connection.execute(
                text("SELECT set_config('app.current_org_id', :o, false)"), {"o": a.org_id}
            )
            for statement, parameters in chosen:
                lines = connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS) " + statement, parameters
                ).fetchall()
                text_plans.append(statement + "\n" + "\n".join(row[0] for row in lines))
        plans[name] = "\n\n".join(text_plans)
    app_engine.dispose()

    out = Path(os.environ["AUDIT_OUTPUT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    indexes = api.sql(
        "SELECT indexdef FROM pg_indexes WHERE tablename IN ('conversations', 'messages') "
        "ORDER BY indexname"
    )
    report = {
        "fixture": {
            "conversations": api.sql("SELECT count(*) FROM conversations")[0][0],
            "messages": api.sql("SELECT count(*) FROM messages")[0][0],
            "tenants": {"a": 7000, "b": 2000, "c": 1000},
        },
        "reads_per_query": READS,
        "limit_p95_ms": LIMIT_MS,
        "environment": {
            "logical_cpus": os.cpu_count(),
            "platform": platform.platform(),
            "server": api.sql("SHOW server_version")[0][0],
            "client": "in-process TestClient inside the QA api container",
        },
        "indexes": [row[0] for row in indexes],
        "results": results,
    }
    (out / "inbox-perf.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "inbox-plans.txt").write_text(
        "\n\n".join(f"===== {name}\n{plan}" for name, plan in plans.items()), encoding="utf-8"
    )
    print(json.dumps(results, indent=1))
    assert all(r["p95_ms"] <= LIMIT_MS for r in results.values()), results
