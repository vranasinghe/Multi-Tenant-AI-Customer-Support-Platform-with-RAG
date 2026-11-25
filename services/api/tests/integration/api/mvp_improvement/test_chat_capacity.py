"""Strict A1 gates: real ASGI overlap, database/RLS/Redis, deterministic no-cost providers."""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from sqlalchemy import event
from starlette.types import Message, Scope

from app.core.config import Settings
from app.integrations.llm import CompletionEvent
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.services.container import AppServices
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.test_conversations import conversation
from tests.integration.api.test_knowledge_documents import ingest, new_bot

pytestmark = pytest.mark.integration
EXPECTED = "Capacity fixture completed [1]."


@pytest.fixture(autouse=True)
def limits(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"
    api_settings.chat_requests_per_minute = 100000
    api_settings.chat_monthly_token_limit = 100000000
    api_settings.chat_monthly_cost_limit_usd = 1000


class Provider:
    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self.hold: asyncio.Event | None = None
        self.started: asyncio.Event | None = None
        self.saturated: asyncio.Event | None = None

    async def stream(
        self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
    ) -> AsyncGenerator[CompletionEvent]:
        assert all("FOREIGN_TENANT_SECRET" not in m["content"] for m in messages)
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active == 3 and self.saturated:
            self.saturated.set()
        try:
            yield CompletionEvent(text=EXPECTED)
            if self.started:
                self.started.set()
            if self.hold:
                await self.hold.wait()
            await asyncio.sleep(0.01)
            yield CompletionEvent(input_tokens=100, output_tokens=10)
        finally:
            self.active -= 1


@dataclass
class PoolWatch:
    checked_out: int = 0
    peak: int = 0
    checkouts: int = 0
    checkins: int = 0
    samples: list[int] = field(default_factory=list)

    def checkout(self, *_: object) -> None:
        self.checked_out += 1
        self.checkouts += 1
        self.peak = max(self.peak, self.checked_out)
        self.samples.append(self.checked_out)

    def checkin(self, *_: object) -> None:
        self.checked_out -= 1
        self.checkins += 1


def save(name: str, result: object) -> None:
    folder = Path(os.environ.get("AUDIT_OUTPUT_DIR", "/tmp/mvp-improvement/AUD-01"))  # noqa: S108
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name + ".json")).write_text(json.dumps(result, indent=2))


def setup(api: Api, runtime: Runtime, job_queue: RecordingJobQueue) -> tuple[Actor, str, Provider]:
    actor = api.signup(org_name="TechMart capacity")
    bot = new_bot(actor)
    ingest(
        api,
        runtime,
        job_queue,
        actor,
        bot,
        "capacity.txt",
        b"Returns policy: unused laptops may be returned within 30 days with a receipt.",
        "text/plain",
    )
    provider = Provider()
    app = cast(FastAPI, api.client.app)
    app.state.services = replace(app.state.services, chat_provider=provider)
    return actor, bot, provider


async def request(
    app: FastAPI,
    actor: Actor,
    path: str,
    *,
    method: str = "POST",
    body: dict[str, Any] | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    sent = False
    chunks: list[bytes] = []
    status = 0
    started = time.perf_counter()
    first_delta: float | None = None
    never = asyncio.Event()

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": json.dumps(body or {"content": "What is the returns policy?"}).encode(),
                "more_body": False,
            }
        await never.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal status, first_delta
        if message["type"] == "http.response.start":
            status = message["status"]
        elif message["type"] == "http.response.body":
            data = message.get("body", b"")
            chunks.append(data)
            if b"event: delta" in data and first_delta is None:
                first_delta = (time.perf_counter() - started) * 1000

    headers = [
        (b"content-type", b"application/json"),
        (b"origin", b"https://app.test"),
        (b"x-requested-with", b"platform"),
    ]
    headers.append(
        (b"authorization", ("Bearer " + token).encode())
        if token
        else (b"cookie", f"__Host-session={actor.cookie}".encode())
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "scheme": "https",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 443),
    }
    async with asyncio.timeout(10):
        await app(scope, receive, send)
    raw = b"".join(chunks).decode()
    terminal = [
        json.loads(f.split("data: ", 1)[1])
        for f in raw.split("\n\n")
        if f.startswith("event: done")
    ]
    errors = "event: error" in raw
    if status == 200 and method == "POST" and path.endswith("/messages"):
        assert len(terminal) == 1 and not errors, raw
        assert terminal[0]["status"] == "complete" and terminal[0]["content"] == EXPECTED, raw
    return {
        "status": status,
        "duration_ms": (time.perf_counter() - started) * 1000,
        "ttft_ms": first_delta,
        "done": terminal[0] if terminal else None,
        "json": json.loads(raw) if raw and not terminal and not raw.startswith("event:") else None,
    }


def percentile(values: list[float], p: float = 0.95) -> float:
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * p)] if ordered else 0


@pytest.mark.parametrize("concurrency", [1, 10, 50, 100])
def test_strict_capacity(
    api: Api,
    runtime: Runtime,
    job_queue: RecordingJobQueue,
    api_settings: Settings,
    concurrency: int,
) -> None:
    actor, bot, provider = setup(api, runtime, job_queue)
    count = max(10, concurrency)
    # Seed IDs without the separate 30/min conversation-creation limit masking send capacity.
    ids = [str(uuid.uuid4()) for _ in range(count)]
    for cid in ids:
        api.sql(
            "INSERT INTO conversations(id,org_id,chatbot_id,channel,created_by) VALUES(:id,:org,:bot,'playground',:user)",
            id=cid,
            org=actor.org_id,
            bot=bot,
            user=actor.user_id,
        )
    app = cast(FastAPI, api.client.app)
    assert api_settings.db_pool_size == 5 and api_settings.db_max_overflow == 5
    assert api_settings.chat_concurrency_per_org == 3
    watch = PoolWatch()
    engine = app.state.engine.sync_engine
    event.listen(engine, "checkout", watch.checkout)
    event.listen(engine, "checkin", watch.checkin)
    overlapping = peak_overlap = 0

    async def scenario() -> list[dict[str, Any]]:
        barrier = asyncio.Barrier(concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def one(cid: str) -> dict[str, Any]:
            nonlocal overlapping, peak_overlap
            async with semaphore:
                await barrier.wait()
                overlapping += 1
                peak_overlap = max(overlapping, peak_overlap)
                try:
                    return await request(
                        app, actor, f"/api/v1/orgs/{actor.org_id}/conversations/{cid}/messages"
                    )
                finally:
                    overlapping -= 1

        return await asyncio.gather(*(one(cid) for cid in ids))

    assert api.client.portal
    start = time.perf_counter()
    rows = api.client.portal.call(scenario)
    elapsed = time.perf_counter() - start
    accepted = [r for r in rows if r["status"] == 200]
    rejected = [r for r in rows if r["status"] in {429, 503}]
    report = {
        "concurrency": concurrency,
        "requests": count,
        "overlap_peak": peak_overlap,
        "provider_peak": provider.peak,
        "success": len(accepted),
        "rejected": len(rejected),
        "failed": count - len(accepted) - len(rejected),
        "successful_p95_ms": percentile([r["duration_ms"] for r in accepted]),
        "rejected_p95_ms": percentile([r["duration_ms"] for r in rejected]),
        "successful_requests_per_second": len(accepted) / elapsed,
        "pool": vars(watch),
        "setup_peak": app.state.services.chat_work.peak,
        "raw": rows,
    }
    save(f"capacity-{concurrency}", report)
    assert peak_overlap == concurrency
    assert len(accepted) >= (count if concurrency == 1 else max(3, count // 4))
    assert len(accepted) + len(rejected) == count
    assert report["successful_p95_ms"] <= 2000 and report["rejected_p95_ms"] <= 3000
    assert watch.checked_out == 0 and watch.checkouts == watch.checkins and watch.peak <= 10
    assert app.state.services.chat_work.active == 0
    assert provider.peak <= 3 and provider.active == 0
    for row in accepted:
        mid = row["done"]["id"]
        assert api.sql("SELECT status,content FROM messages WHERE id=:id", id=mid) == [
            ("complete", EXPECTED)
        ]
        assert api.sql("SELECT state,charged_tokens FROM chat_usage WHERE id=:id", id=mid) == [
            ("settled", 110)
        ]
    assert api.sql(
        "SELECT count(*) FROM messages WHERE org_id=:org AND role='assistant'", org=actor.org_id
    )[0][0] == len(accepted)

    async def clean() -> None:
        services: AppServices = app.state.services
        assert await services.redis.zcard(f"chat:{{{actor.org_id}}}:active") == 0
        assert not await services.redis.keys(f"chat:{{{actor.org_id}}}:conversation:*")

    api.client.portal.call(clean)


def test_second_tenant_fairness(api: Api, runtime: Runtime, job_queue: RecordingJobQueue) -> None:
    a, bot, provider = setup(api, runtime, job_queue)
    b, bbot, _ = setup(api, runtime, job_queue)

    # Install one provider that only pauses A, leaving B's valid generation independent.
    class FairProvider(Provider):
        async def stream(
            self, messages: list[dict[str, str]], *, model: str, max_tokens: int, temperature: float
        ) -> AsyncGenerator[CompletionEvent]:
            if "TENANT_A_HOLD" in messages[-1]["content"]:
                async for part in provider.stream(
                    messages, model=model, max_tokens=max_tokens, temperature=temperature
                ):
                    yield part
            else:
                yield CompletionEvent(text=EXPECTED)
                yield CompletionEvent(input_tokens=100, output_tokens=10)

    app = cast(FastAPI, api.client.app)
    app.state.services = replace(app.state.services, chat_provider=FairProvider())
    aids = [conversation(a, bot) for _ in range(10)]
    bids = [conversation(b, bbot) for _ in range(5)]
    base = f"/orgs/{b.org_id}/chatbots/{bbot}"
    b.patch(base, {"status": "active"})
    b.post(base + "/domains", {"origin": "http://localhost:3101"})
    domain = b.get(base + "/widget-config").json()["domains"][0]
    b.post(base + f"/domains/{domain['id']}/verify")
    key = b.get(base).json()["public_key"]
    watch = PoolWatch()
    event.listen(app.state.engine.sync_engine, "checkout", watch.checkout)
    event.listen(app.state.engine.sync_engine, "checkin", watch.checkin)

    async def scenario() -> dict[str, Any]:
        provider.hold, provider.started = asyncio.Event(), asyncio.Event()
        provider.saturated = asyncio.Event()
        path = f"/api/v1/orgs/{b.org_id}/chatbots"
        idle = [(await request(app, b, path, method="GET"))["duration_ms"] for _ in range(20)]
        barrier = asyncio.Barrier(10)

        async def hold_a(cid: str) -> dict[str, Any]:
            await barrier.wait()
            return await request(
                app,
                a,
                f"/api/v1/orgs/{a.org_id}/conversations/{cid}/messages",
                body={"content": "Returns policy? TENANT_A_HOLD"},
            )

        busy = [asyncio.create_task(hold_a(cid)) for cid in aids]
        await asyncio.wait_for(provider.saturated.wait(), 2)
        saturated = provider.active
        assert watch.checked_out == 0, "Provider-only wait retained a checkout"
        reads = [await request(app, b, path, method="GET") for _ in range(20)]
        chats = [
            await request(app, b, f"/api/v1/orgs/{b.org_id}/conversations/{cid}/messages")
            for cid in bids
        ]
        mixed = await asyncio.gather(
            *(
                request(app, b, f"/api/v1/orgs/{b.org_id}/conversations/{bids[0]}", method="GET")
                for _ in range(4)
            ),
            *(
                request(
                    app,
                    b,
                    "/public/v1/widget/sessions",
                    body={"key": key, "parent_origin": "http://localhost:3101"},
                )
                for _ in range(4)
            ),
        )
        assert all(r["status"] == 200 for r in mixed)
        token = mixed[-1]["json"]["token"]
        history = await request(app, b, "/public/v1/chat", method="GET", token=token)
        assert history["status"] == 200
        provider.hold.set()
        arows = await asyncio.gather(*busy)
        assert sum(r["status"] == 200 for r in arows) >= 3
        return {
            "mixed_statuses": [r["status"] for r in mixed],
            "public_history_status": history["status"],
            "saturated_provider_active": saturated,
            "a_statuses": [r["status"] for r in arows],
            "idle_p95_ms": percentile(idle),
            "busy_read_p95_ms": percentile([r["duration_ms"] for r in reads]),
            "read_statuses": [r["status"] for r in reads],
            "chat_statuses": [r["status"] for r in chats],
            "pool": vars(watch),
        }

    assert api.client.portal
    report = api.client.portal.call(scenario)
    save("fairness", report)
    assert report["read_statuses"] == [200] * 20 and report["chat_statuses"] == [200] * 5
    assert report["busy_read_p95_ms"] <= 1000
    assert report["busy_read_p95_ms"] <= 2 * report["idle_p95_ms"] + 100
    assert watch.checked_out == 0 and watch.checkouts == watch.checkins
