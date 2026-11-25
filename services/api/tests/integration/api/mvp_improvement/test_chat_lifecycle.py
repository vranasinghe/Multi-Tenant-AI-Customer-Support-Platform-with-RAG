"""A1 authorization boundaries, single-checkout paths and cancellation containment."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from typing import Any, cast

import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.errors import ApiError
from app.rag.embeddings import OpenAICompatibleEmbedder
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.schemas.conversations import SendMessage
from app.services import conversations
from app.services.chat_work import ChatWork
from tests.integration.api.conftest import Api
from tests.integration.api.mvp_improvement.test_chat_capacity import request, save, setup
from tests.integration.api.test_conversations import conversation, done, send

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def enable(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"


@pytest.fixture
def one_pool(api_settings: Settings) -> None:
    api_settings.db_pool_size = 1
    api_settings.db_max_overflow = 0


@pytest.mark.usefixtures("one_pool")
def test_pool_one_idle_touch_widget_and_reads(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    actor, bot, _ = setup(api, runtime, job_queue)
    app = cast(FastAPI, api.client.app)
    assert app.state.engine.pool.size() == 1
    api.sql(
        "UPDATE sessions SET last_seen_at=now()-interval '10 minutes' WHERE user_id=:id",
        id=actor.user_id,
    )
    conv = conversation(actor, bot)
    assert done(send(actor, conv, "Returns policy?"))["status"] == "complete"
    assert actor.get(f"/orgs/{actor.org_id}/conversations/{conv}").status_code == 200
    assert actor.get(f"/orgs/{actor.org_id}/chatbots/{bot}/conversations").status_code == 200
    base = f"/orgs/{actor.org_id}/chatbots/{bot}"
    assert actor.patch(base, {"status": "active"}).status_code == 200
    assert actor.post(base + "/widget-sessions").status_code == 201
    assert actor.post(base + "/domains", {"origin": "http://localhost:3101"}).status_code == 201
    domain = actor.get(base + "/widget-config").json()["domains"][0]
    assert actor.post(base + f"/domains/{domain['id']}/verify").status_code == 200
    key = actor.get(base).json()["public_key"]
    session = api.client.post(
        "/public/v1/widget/sessions", json={"key": key, "parent_origin": "http://localhost:3101"}
    )
    assert session.status_code == 200
    original = session.json()
    resumed = api.client.post(
        "/public/v1/widget/sessions",
        json={
            "key": key,
            "parent_origin": "http://localhost:3101",
            "resume_token": original["resume_token"],
        },
    )
    assert resumed.status_code == 200
    token = resumed.json()["token"]
    headers = {"Authorization": "Bearer " + token}
    assert api.client.get("/public/v1/chat", headers=headers).status_code == 200
    assert (
        done(
            api.client.post(
                "/public/v1/chat/messages", headers=headers, json={"content": "Returns policy?"}
            )
        )["status"]
        == "complete"
    )
    assert app.state.engine.pool.checkedout() == 0
    api.sql(
        "UPDATE sessions SET last_seen_at=now()-interval '10 minutes' WHERE user_id=:id",
        id=actor.user_id,
    )

    async def stale_burst() -> None:
        barrier = asyncio.Barrier(10)

        async def one() -> int:
            await barrier.wait()
            result = await request(
                app,
                actor,
                f"/api/v1/orgs/{actor.org_id}/chatbots/{bot}/conversations",
                method="GET",
            )
            return int(result["status"])

        assert await asyncio.gather(*(one() for _ in range(10))) == [200] * 10

    assert api.client.portal
    api.client.portal.call(stale_burst)
    save(
        "pool-one",
        {
            "pool_size": 1,
            "overflow": 0,
            "checked_out_after": 0,
            "idle_touch_create_send_transcript_list_issue_bootstrap_resume_history": "PASS",
        },
    )


@pytest.mark.parametrize("mutation", ["session", "member", "role", "org", "key", "domain"])
def test_revalidate_after_embedding(
    api: Api,
    runtime: Runtime,
    job_queue: RecordingJobQueue,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    actor, bot, provider = setup(api, runtime, job_queue)
    conv = conversation(actor, bot)
    peer = api.signup()
    api.sql(
        "INSERT INTO memberships(id,org_id,user_id,role) VALUES(:id,:org,:user,'owner')",
        id=str(uuid.uuid4()),
        org=actor.org_id,
        user=peer.user_id,
    )
    token: str | None = None
    if mutation in {"key", "domain"}:
        base = f"/orgs/{actor.org_id}/chatbots/{bot}"
        actor.patch(base, {"status": "active"})
        actor.post(base + "/domains", {"origin": "http://localhost:3101"})
        domain = actor.get(base + "/widget-config").json()["domains"][0]
        actor.post(base + f"/domains/{domain['id']}/verify")
        key = actor.get(base).json()["public_key"]
        session = api.client.post(
            "/public/v1/widget/sessions",
            json={"key": key, "parent_origin": "http://localhost:3101"},
        ).json()
        token = session["token"]
    original = ChatWork.query

    async def query(
        self: ChatWork, embedder: Any, question: str, deadline_seconds: float
    ) -> list[float]:
        assert cast(FastAPI, api.client.app).state.engine.pool.checkedout() == 0
        if mutation == "session":
            api.sql("UPDATE sessions SET revoked_at=now() WHERE user_id=:id", id=actor.user_id)
        elif mutation == "member":
            api.sql(
                "DELETE FROM memberships WHERE org_id=:org AND user_id=:id",
                org=actor.org_id,
                id=actor.user_id,
            )
        elif mutation == "role":
            api.sql(
                "UPDATE memberships SET role='viewer' WHERE org_id=:org AND user_id=:id",
                org=actor.org_id,
                id=actor.user_id,
            )
        elif mutation == "org":
            api.sql("UPDATE organizations SET status='restricted' WHERE id=:id", id=actor.org_id)
        elif mutation == "key":
            api.sql(
                "UPDATE chatbots SET public_key=:key WHERE id=:id",
                key="pk_live_RRRRRRRRRRRRRRRRRRRRRRRR",
                id=bot,
            )
        else:
            api.sql("DELETE FROM chatbot_domains WHERE chatbot_id=:id", id=bot)
        return await original(self, embedder, question, deadline_seconds)

    monkeypatch.setattr(ChatWork, "query", query)
    response = (
        api.client.post(
            "/public/v1/chat/messages",
            headers={"Authorization": "Bearer " + token},
            json={"content": "Returns policy?"},
        )
        if token
        else send(actor, conv, "Returns policy?")
    )
    assert response.status_code in {401, 403, 404}
    assert provider.peak == 0
    assert api.sql("SELECT count(*) FROM chat_usage WHERE org_id=:org", org=actor.org_id) == [(0,)]
    assert api.sql("SELECT count(*) FROM messages WHERE org_id=:org", org=actor.org_id) == [(0,)]
    app = cast(FastAPI, api.client.app)
    assert app.state.engine.pool.checkedout() == 0 and app.state.services.chat_work.active == 0
    assert api.client.portal

    async def clean() -> None:
        assert await app.state.services.redis.zcard(f"chat:{{{actor.org_id}}}:active") == 0

    api.client.portal.call(clean)


@pytest.mark.usefixtures("one_pool")
def test_pool_wait_is_bounded_controlled_503(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    actor, bot, _ = setup(api, runtime, job_queue)
    conv = conversation(actor, bot)
    app = cast(FastAPI, api.client.app)

    async def scenario() -> dict[str, Any]:
        async with app.state.engine.connect():
            return await request(
                app, actor, f"/api/v1/orgs/{actor.org_id}/conversations/{conv}/messages"
            )

    assert api.client.portal
    result = api.client.portal.call(scenario)
    assert result["status"] == 503 and result["duration_ms"] <= 3000
    assert result["json"]["code"] == "chat_unavailable"
    assert app.state.engine.pool.checkedout() == 0
    save("bounded-pool-wait", result)


def test_remote_query_cancellation_and_timeout_are_reaped(api: Api) -> None:  # noqa: PLR0915
    app = cast(FastAPI, api.client.app)
    work: ChatWork = app.state.services.chat_work

    async def scenario() -> list[dict[str, Any]]:
        connected = asyncio.Event()
        release = asyncio.Event()

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                await reader.readuntil(b"\r\n\r\n")
                connected.set()
                await release.wait()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        embedder = OpenAICompatibleEmbedder(
            base_url=f"http://127.0.0.1:{port}/v1",
            api_key="fictional",
            model_id="fixture",
            dimensions=1536,
            batch_size=1,
            timeout=10,
            allow_insecure_local=True,
        )
        reports = []
        try:
            for _ in range(5):
                connected.clear()

                async def run() -> list[float]:
                    async with work.setup():
                        return await work.query(embedder, "fictional", 5)

                task = asyncio.create_task(run())
                await asyncio.wait_for(connected.wait(), 3)
                assert work.active == 1 and len(work.children) == 1
                assert app.state.engine.pool.checkedout() == 0
                started = time.perf_counter()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                reports.append(
                    {
                        "cancel_cleanup_ms": (time.perf_counter() - started) * 1000,
                        "children_after": len(work.children),
                        "setup_after": work.active,
                    }
                )
                assert not work.children and work.active == 0
            for _ in range(5):
                async with work.setup():
                    with pytest.raises(TimeoutError):
                        await work.query(embedder, "fictional", 0.25)
                assert not work.children and work.active == 0
            # No ChatWork parent timeout: the child must enforce its own hard wall deadline.
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "app.services.query_process",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                async with asyncio.timeout(3):
                    await proc.communicate(
                        json.dumps(
                            {
                                "base_url": f"http://127.0.0.1:{port}/v1",
                                "api_key": "fictional",
                                "model_id": "fixture",
                                "dimensions": 1536,
                                "batch_size": 1,
                                "timeout": 0.25,
                                "allow_insecure_local": True,
                                "question": "fictional",
                            }
                        ).encode()
                    )
                assert proc.returncode == 124
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
            return reports
        finally:
            release.set()
            server.close()
            await server.wait_closed()

    assert api.client.portal
    report = api.client.portal.call(scenario)
    assert all(r["cancel_cleanup_ms"] <= 2000 for r in report)
    save("query-cancellation", report)


def test_remote_query_success_uses_existing_adapter(api: Api) -> None:
    app = cast(FastAPI, api.client.app)
    work: ChatWork = app.state.services.chat_work

    async def scenario() -> None:
        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = int(
                next(
                    line.split(b":", 1)[1]
                    for line in headers.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                )
            )
            payload = json.loads(await reader.readexactly(length))
            assert payload["input"] == ["fictional"]
            body = json.dumps({"data": [{"index": 0, "embedding": [1.0] + [0.0] * 1535}]}).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        try:
            port = server.sockets[0].getsockname()[1]
            e = OpenAICompatibleEmbedder(
                base_url=f"http://127.0.0.1:{port}/v1",
                api_key="fictional",
                model_id="fixture",
                dimensions=1536,
                batch_size=1,
                timeout=2,
                allow_insecure_local=True,
            )
            async with work.setup():
                assert await work.query(e, "fictional", 3) == [1.0] + [0.0] * 1535
            assert not work.children and work.active == 0
        finally:
            server.close()
            await server.wait_closed()

    assert api.client.portal
    api.client.portal.call(scenario)


def test_setup_capacity_is_bounded_and_releases(api: Api) -> None:
    from contextlib import AsyncExitStack

    app = cast(FastAPI, api.client.app)
    work: ChatWork = app.state.services.chat_work

    async def scenario() -> None:
        async with AsyncExitStack() as stack:
            for _ in range(work.capacity):
                await stack.enter_async_context(work.setup())
            with pytest.raises(ApiError, match="chat_unavailable"):
                async with work.setup():
                    pytest.fail("Unbounded setup admission")
        assert work.active == 0

    assert api.client.portal
    api.client.portal.call(scenario)


def test_cancel_before_stream_settles_usage(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    actor, bot, _ = setup(api, runtime, job_queue)
    cid = conversation(actor, bot)
    app = cast(FastAPI, api.client.app)

    async def scenario() -> str:
        turn = await conversations.prepare(
            app.state.services,
            uuid.UUID(actor.org_id),
            uuid.UUID(cid),
            SendMessage(content="Returns policy?"),
        )
        await conversations.close_pending_turn(app.state.services, turn)
        assert await app.state.services.redis.zcard(f"chat:{{{actor.org_id}}}:active") == 0
        return str(turn.message_id)

    assert api.client.portal
    mid = api.client.portal.call(scenario)
    assert api.sql("SELECT status FROM messages WHERE id=:id", id=mid) == [("interrupted",)]
    assert api.sql("SELECT state,charged_tokens>0 FROM chat_usage WHERE id=:id", id=mid) == [
        ("settled", True)
    ]


def test_cancellation_during_embedding_releases_admission(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, bot, _ = setup(api, runtime, job_queue)
    cid = conversation(actor, bot)
    app = cast(FastAPI, api.client.app)

    async def scenario() -> None:
        entered = asyncio.Event()

        async def block(
            self: ChatWork, embedder: Any, question: str, deadline_seconds: float
        ) -> list[float]:
            assert app.state.engine.pool.checkedout() == 0
            entered.set()
            await asyncio.Event().wait()
            return []

        monkeypatch.setattr(ChatWork, "query", block)
        task = asyncio.create_task(
            conversations.prepare(
                app.state.services,
                uuid.UUID(actor.org_id),
                uuid.UUID(cid),
                SendMessage(content="Returns policy?"),
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert app.state.services.chat_work.active == 0
        assert app.state.engine.pool.checkedout() == 0
        assert await app.state.services.redis.zcard(f"chat:{{{actor.org_id}}}:active") == 0

    assert api.client.portal
    api.client.portal.call(scenario)
    assert api.sql("SELECT count(*) FROM chat_usage WHERE org_id=:org", org=actor.org_id) == [(0,)]
