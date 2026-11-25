"""Independent audit harness. All writes use the inherited disposable test database."""

# mypy: ignore-errors
# ruff: noqa: PLR0915 -- audit workflows intentionally retain a linear evidence sequence
from __future__ import annotations

import asyncio
import json
import os
import resource
import time
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.config import Settings
from app.integrations.llm import CompletionEvent
from tests.integration.api.test_conversations import conversation, done, send
from tests.integration.api.test_knowledge_documents import docs_path, ingest, new_bot
from tests.support.documents import make_docx, make_pdf

pytestmark = pytest.mark.integration
OUT = Path(os.environ.get("AUDIT_OUTPUT_DIR", "/tmp/implementation_audit"))  # noqa: S108 -- isolated container audit output, never used for credentials


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, indent=2, default=str))


@pytest.fixture(autouse=True)
def config(api_settings: Settings):
    api_settings.llm_provider = "demo"
    api_settings.chat_requests_per_minute = 100000
    api_settings.chat_monthly_token_limit = 100000000
    api_settings.chat_monthly_cost_limit_usd = 1000


class FixtureProvider:
    async def stream(self, messages, *, model, max_tokens, temperature):
        await asyncio.sleep(0.01)
        yield CompletionEvent(text="Infrastructure fixture response [1].")
        yield CompletionEvent(input_tokens=100, output_tokens=10)


def seed(api, runtime, job_queue):
    fixture = json.loads(Path(__file__).with_name("dataset.json").read_text())
    actors = {name: api.signup(org_name=name) for name in ["TechMart", "SkillHub"]}
    bots = {name: new_bot(actor) for name, actor in actors.items()}
    docs = {}
    timings = []
    for d in fixture["corpus"]:
        start = time.perf_counter()
        row = ingest(
            api,
            runtime,
            job_queue,
            actors[d["organization"]],
            bots[d["organization"]],
            d["filename"],
            d["content"].encode(),
            "text/plain",
        )
        assert row["status"] == "ready"
        docs[d["filename"]] = row["id"]
        timings.append((time.perf_counter() - start) * 1000)
    return fixture, actors, bots, docs, timings


def test_business_workflow_and_100_case_evaluation(api, runtime, job_queue):
    fixture, actors, bots, docs, timings = seed(api, runtime, job_queue)
    evidence = []
    for org in actors:
        stored = api.sql(
            "SELECT count(*),min(vector_dims(embedding)),max(vector_dims(embedding)) FROM document_chunks WHERE org_id=:org",
            org=actors[org].org_id,
        )
        assert stored[0][0] > 0 and stored[0][1:] == (1536, 1536)
        evidence.append({"step": "stored_chunks_and_dimensions", "org": org, "rows": stored})
    a, b = actors["TechMart"], actors["SkillHub"]
    base = docs_path(a, bots["TechMart"])
    # Every requested manipulated identifier family is checked against both path scopes.
    attempts = [
        a.get(f"/orgs/{b.org_id}/chatbots/{bots['SkillHub']}"),
        a.get(base + f"/documents/{docs['skillhub-refunds.txt']}"),
        a.post(base + "/retrieval/search", {"query": "SkillHub refund"}),
        a.patch(f"/orgs/{b.org_id}/chatbots/{bots['SkillHub']}", {"name": "stolen"}),
    ]
    assert (
        attempts[0].status_code == 404
        and attempts[1].status_code == 404
        and attempts[3].status_code == 404
    )
    assert all(
        c["document_id"]
        not in {docs[d["filename"]] for d in fixture["corpus"] if d["organization"] == "SkillHub"}
        for c in attempts[2].json()["results"]
    )
    # PDF/DOCX go through the real parser/indexer, not a ready-status-only assertion.
    for filename, data, ctype in [
        ("audit.pdf", make_pdf(["Audit PDF product support evidence."]), "application/pdf"),
        (
            "audit.docx",
            make_docx([("p", "Audit DOCX product support evidence.")]),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]:
        row = ingest(api, runtime, job_queue, a, bots["TechMart"], filename, data, ctype)
        assert (
            api.sql("SELECT count(*) FROM document_chunks WHERE document_id=:doc", doc=row["id"])[
                0
            ][0]
            > 0
        )
        evidence.append(
            {"step": "parsed_and_persisted", "filename": filename, "status": row["status"]}
        )
    # Distinct conversations and cross-tenant conversation IDOR.
    conv = conversation(a, bots["TechMart"])
    foreign = conversation(b, bots["SkillHub"])
    assert a.get(f"/orgs/{a.org_id}/conversations/{foreign}").status_code == 404
    reply = done(send(a, conv, "What is the return window for an unused laptop?"))
    assert reply["status"] == "complete"
    assert (
        a.get(f"/orgs/{a.org_id}/conversations/{conv}").json()["messages"][-1]["id"] == reply["id"]
    )
    assert (
        a.patch(
            base, {"status": "active", "widget_settings": {"primary_color": "#13579B"}}
        ).status_code
        == 200
    )
    assert a.get(base).json()["widget_settings"]["primary_color"] == "#13579B"
    # Widget issuance/domain configuration uses real DB/API checks. Full browser embed is separate.
    assert a.post(base + "/domains", {"origin": "http://localhost:3101"}).status_code == 201
    domain = a.get(base + "/widget-config").json()["domains"][0]
    assert a.post(base + f"/domains/{domain['id']}/verify").status_code == 200
    key = a.get(base).json()["public_key"]
    frame = api.client.get(
        f"/widget/frame/{key}",
        params={"parent_origin": "http://localhost:3101", "instance": "audit"},
    )
    assert frame.status_code == 200
    session = api.client.post(
        "/public/v1/widget/sessions", json={"key": key, "parent_origin": "http://localhost:3101"}
    ).json()
    widget = api.client.post(
        "/public/v1/chat/messages",
        headers={"Authorization": "Bearer " + session["token"]},
        json={"content": "What is the return window for an unused laptop?"},
    )
    assert done(widget)["status"] == "complete"
    # Do not persist any bearer credentials in audit artifacts.
    evidence.extend(
        [
            {"step": "orgs_created", "organizations": list(actors)},
            {"step": "identifier_manipulations", "statuses": [r.status_code for r in attempts]},
            {"step": "chat_persistence", "status": reply["status"], "provider": "demo"},
            {"step": "branding", "color": "#13579B"},
            {"step": "embed_frame", "status": frame.status_code},
            {"step": "public_chat", "status": widget.status_code, "provider": "demo"},
        ]
    )
    results = []
    hits = leaks = known = 0
    for case in fixture["cases"]:
        actor = actors[case["organization"]]
        bot = bots[case["organization"]]
        question = case["question"]
        query = question
        if case["conversation_history"]:
            query = case["conversation_history"][0]["content"] + "\n" + question
        start = time.perf_counter()
        response = actor.post(
            docs_path(actor, bot) + "/retrieval/search",
            {"query": query, "top_k": 5, "mode": "hybrid"},
        )
        assert response.status_code == 200, response.text
        chunks = response.json()["results"]
        elapsed = (time.perf_counter() - start) * 1000
        own = {
            docs[d["filename"]]
            for d in fixture["corpus"]
            if d["organization"] == case["organization"]
        }
        leaked = [
            c
            for c in chunks
            if c["document_id"] not in own
            and c["document_title"] not in {"audit.pdf", "audit.docx"}
        ]
        leaks += len(leaked)
        expected = case["expected_document"]
        hit = None
        if expected:
            known += 1
            hit = any(
                c["document_id"] == docs[expected]
                and all(p.lower() in c["content"].lower() for p in case["expected_answer_phrases"])
                for c in chunks
            )
            hits += bool(hit)
        # A separate transport-fixture generation is recorded, NEVER graded as real answer quality.
        cid = str(uuid.uuid4())
        api.sql(
            "INSERT INTO conversations(id,org_id,chatbot_id,channel,created_by) VALUES(:id,:org,:bot,'playground',:user)",
            id=cid,
            org=actor.org_id,
            bot=bot,
            user=actor.user_id,
        )
        generated = done(send(actor, cid, question, context_messages=0))
        results.append(
            {
                **case,
                "retrieved_chunks": chunks,
                "generated_answer": None,
                "actual_citations": None,
                "status": "BLOCKED",
                "failure_reason": "No real semantic embedding or LLM provider credentials; transport fixture is not a live evaluation.",
                "retrieval_hit_at_5": hit,
                "retrieval_latency_ms": round(elapsed, 3),
                "leaked_chunks": len(leaked),
                "mock_generated_answer": generated["content"],
                "mock_citations": generated["citations"],
                "mock_status": generated["status"],
                "history_note": "Follow-up retrieval prepends prior question; generation fixture does not replay history.",
            }
        )
    assert leaks == 0
    # Delete and verify physical row removal AND absence from subsequent retrieval.
    target = docs["techmart-returns.txt"]
    assert a.delete(base + f"/documents/{target}").status_code == 204
    remaining = api.sql("SELECT count(*) FROM document_chunks WHERE document_id=:id", id=target)[0][
        0
    ]
    post = a.post(
        base + "/retrieval/search", {"query": "unused laptops return 30 days", "top_k": 5}
    ).json()["results"]
    assert remaining == 0 and all(c["document_id"] != target for c in post)
    evidence.append(
        {
            "step": "deletion_verified",
            "remaining_chunks": remaining,
            "stale_results": sum(c["document_id"] == target for c in post),
        }
    )
    save("business_workflow.json", {"evidence": evidence, "ingestion_ms": timings})
    save("rag_results.json", results)
    save(
        "rag_metrics.json",
        {
            "dataset_size": len(results),
            "answerable_cases": known,
            "recall_at_5_hits": hits,
            "recall_at_5": hits / known,
            "cross_tenant_leaked_chunks": leaks,
            "embedder": "hash-v1",
            "provider": "demo",
            "live_answer_correctness": None,
            "live_faithfulness": None,
            "live_citation_accuracy": None,
            "live_refusal_rate": None,
            "live_status": "BLOCKED",
        },
    )


def test_staged_isolated_performance(api, runtime, job_queue, api_settings):
    actor = api.signup(org_name="TechMart performance")
    bot = new_bot(actor)
    ingest(
        api,
        runtime,
        job_queue,
        actor,
        bot,
        "performance.txt",
        b"TechMart returns unused laptops within 30 days with a receipt.",
        "text/plain",
    )
    services = api.client.app.state.services
    api.client.app.state.services = replace(services, chat_provider=FixtureProvider())
    measurements = []
    for concurrency in [10] if os.environ.get("AUDIT_CONFIRM_POOL") else [1, 10, 50, 100]:
        count = max(10, concurrency)
        ids = [str(uuid.uuid4()) for _ in range(count)]
        for cid in ids:
            api.sql(
                "INSERT INTO conversations(id,org_id,chatbot_id,channel,created_by) VALUES(:id,:org,:bot,'playground',:user)",
                id=cid,
                org=actor.org_id,
                bot=bot,
                user=actor.user_id,
            )

        async def scenario(concurrency=concurrency, ids=ids):
            semaphore = asyncio.Semaphore(concurrency)

            async def one(cid):
                async with semaphore:
                    t = time.perf_counter()
                    events = []
                    status = 0
                    delivered = False
                    wait = asyncio.Event()

                    async def receive():
                        nonlocal delivered
                        if not delivered:
                            delivered = True
                            return {
                                "type": "http.request",
                                "body": b'{"content":"What is the returns policy?"}',
                                "more_body": False,
                            }
                        await wait.wait()
                        return {"type": "http.disconnect"}

                    async def send_frame(message):
                        nonlocal status
                        if message["type"] == "http.response.start":
                            status = message["status"]
                        if message["type"] == "http.response.body":
                            body = message.get("body", b"")
                            if b"event: delta" in body:
                                events.append((time.perf_counter() - t) * 1000)

                    scope = {
                        "type": "http",
                        "asgi": {"version": "3.0", "spec_version": "2.4"},
                        "http_version": "1.1",
                        "scheme": "https",
                        "method": "POST",
                        "path": f"/api/v1/orgs/{actor.org_id}/conversations/{cid}/messages",
                        "query_string": b"",
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"x-requested-with", b"platform"),
                            (b"origin", b"https://app.test"),
                            (b"cookie", f"__Host-session={actor.cookie}".encode()),
                        ],
                        "client": ("127.0.0.1", 1),
                        "server": ("testserver", 443),
                    }
                    await api.client.app(scope, receive, send_frame)
                    return {
                        "status": status,
                        "duration_ms": (time.perf_counter() - t) * 1000,
                        "ttft_ms": events[0] if events else None,
                    }

            tasks = [asyncio.create_task(one(cid)) for cid in ids]
            _, pending = await asyncio.wait(tasks, timeout=40)
            for task in pending:
                task.cancel()
            raw = await asyncio.gather(*tasks, return_exceptions=True)
            return [
                r
                if isinstance(r, dict)
                else {
                    "status": 0,
                    "duration_ms": 40000,
                    "ttft_ms": None,
                    "error": "audit deadline/cancellation",
                }
                for r in raw
            ]

        usage0 = resource.getrusage(resource.RUSAGE_SELF)
        start = time.perf_counter()
        rows = api.client.portal.call(scenario)
        duration = time.perf_counter() - start
        usage1 = resource.getrusage(resource.RUSAGE_SELF)

        def pct(vals, p):
            vals = sorted(vals)
            return vals[min(len(vals) - 1, int((len(vals) - 1) * p))] if vals else None

        success = [r for r in rows if r["status"] == 200]
        lat = [r["duration_ms"] for r in rows]
        ttft = [r["ttft_ms"] for r in success if r["ttft_ms"] is not None]
        measurements.append(
            {
                "concurrency": concurrency,
                "requests": count,
                "statuses": {
                    str(code): sum(r["status"] == code for r in rows)
                    for code in {r["status"] for r in rows}
                },
                "p50_ms": pct(lat, 0.5),
                "p95_ms": pct(lat, 0.95),
                "successful_ttft_p50_ms": pct(ttft, 0.5),
                "successful_ttft_p95_ms": pct(ttft, 0.95),
                "successful_requests_per_second": len(success) / duration,
                "http_error_rate": 1 - len(success) / count,
                "server_5xx_rate": sum(r["status"] >= 500 for r in rows) / count,
                "cpu_seconds": usage1.ru_utime
                + usage1.ru_stime
                - usage0.ru_utime
                - usage0.ru_stime,
                "peak_process_rss_kib": usage1.ru_maxrss,
                "scope": "ASGI app + real isolated Postgres/Redis; fixture LLM; default org concurrency cap 3; no proxy/browser/provider network",
                "raw": rows,
            }
        )
    save(
        "performance_confirmation.json"
        if os.environ.get("AUDIT_CONFIRM_POOL")
        else "performance.json",
        measurements,
    )
    if os.environ.get("AUDIT_CONFIRM_POOL"):
        assert all(row["server_5xx_rate"] == 0 for row in measurements), (
            "Concurrent chat must be admitted or rate-limited, not fail with server errors"
        )
