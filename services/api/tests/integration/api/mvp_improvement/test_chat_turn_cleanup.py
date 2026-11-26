"""PERF-01 (A6.1): the cleanup after a streamed answer runs only when something is left to clean.

A turn that committed its final state and released its lease needs nothing more. Every other
ending must still mark the pending message and usage terminal and free the lease.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import Engine, event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.rag.queue import RecordingJobQueue
from app.rag.runtime import Runtime
from app.schemas.conversations import SendMessage
from app.services import conversations
from tests.integration.api.conftest import Actor, Api
from tests.integration.api.mvp_improvement.test_chat_capacity import setup
from tests.integration.api.test_conversations import conversation, done, send

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def demo(api_settings: Settings) -> None:
    api_settings.llm_provider = "demo"


@pytest.fixture
def work(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Statements and Redis lease releases, in order."""
    seen: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        seen.append(re.sub(r"\s+", " ", statement).strip())

    original = Redis.eval

    async def counting(self: Redis, script: str, *args: Any) -> Any:
        if "ZREM'" in script and "ZADD" not in script:
            seen.append("LEASE RELEASE")
        return await original(self, script, *args)

    monkeypatch.setattr(Redis, "eval", counting)
    event.listen(Engine, "before_cursor_execute", record)
    yield seen
    event.remove(Engine, "before_cursor_execute", record)


def prepared(api: Api, runtime: Runtime, job_queue: RecordingJobQueue) -> tuple[Actor, str]:
    actor, bot, _ = setup(api, runtime, job_queue)
    return actor, conversation(actor, bot)


def state(api: Api, conversation_id: str) -> tuple[Any, Any]:
    [message] = api.sql(
        "SELECT status, error_code FROM messages WHERE conversation_id = :c AND role = 'assistant'",
        c=conversation_id,
    )
    [usage] = api.sql(
        "SELECT state, charged_tokens FROM chat_usage WHERE conversation_id = :c",
        c=conversation_id,
    )
    return tuple(message), tuple(usage)


def leases(api: Api, actor: Actor) -> int:
    app = cast(FastAPI, api.client.app)
    assert api.client.portal

    async def count() -> int:
        return int(await app.state.services.redis.zcard(f"chat:{{{actor.org_id}}}:active"))

    return api.client.portal.call(count)


def after_finalization(work: list[str]) -> list[str]:
    final = next(i for i, s in enumerate(work) if s.startswith("UPDATE chat_usage SET charged"))
    return work[final + 1 :]


def test_a_completed_answer_is_finalized_and_released_exactly_once(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, work: list[str]
) -> None:
    actor, conv = prepared(api, runtime, job_queue)
    work.clear()

    answer = done(send(actor, conv, "What is the returns policy?"))

    assert answer["status"] == "complete"
    assert after_finalization(work) == ["LEASE RELEASE"], work
    assert state(api, conv)[0] == ("complete", None) and state(api, conv)[1][0] == "settled"
    assert leases(api, actor) == 0


def test_a_failed_finalization_is_still_marked_terminal(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, conv = prepared(api, runtime, job_queue)
    original = AsyncSession.commit
    commits: list[int] = []

    async def failing_second(self: AsyncSession) -> None:
        commits.append(1)
        if len(commits) == 2:  # 1: the turn is recorded; 2: finalization
            raise RuntimeError("simulated commit failure")
        await original(self)

    monkeypatch.setattr(AsyncSession, "commit", failing_second)

    send(actor, conv, "What is the returns policy?")

    message, usage = state(api, conv)
    assert message == ("interrupted", "client_disconnected")
    assert usage[0] == "settled" and usage[1] > 0  # uncertain usage stays charged
    assert leases(api, actor) == 0


def test_a_failed_release_is_tried_again(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    actor, conv = prepared(api, runtime, job_queue)
    original = Redis.eval
    failures = [1]

    async def flaky(self: Redis, script: str, *args: Any) -> Any:
        if "ZREM'" in script and "ZADD" not in script and failures:
            failures.pop()
            raise RedisConnectionError("simulated")
        return await original(self, script, *args)

    monkeypatch.setattr(Redis, "eval", flaky)

    assert done(send(actor, conv, "What is the returns policy?"))["status"] == "complete"

    assert not failures and leases(api, actor) == 0


def test_a_stream_that_never_starts_is_marked_interrupted(
    api: Api, runtime: Runtime, job_queue: RecordingJobQueue
) -> None:
    actor, conv = prepared(api, runtime, job_queue)
    app = cast(FastAPI, api.client.app)

    async def scenario() -> None:
        turn = await conversations.prepare(
            app.state.services,
            uuid.UUID(actor.org_id),
            uuid.UUID(conv),
            SendMessage(content="Returns policy?"),
        )
        await conversations.close_pending_turn(app.state.services, turn)
        await conversations.close_pending_turn(app.state.services, turn)  # harmless twice

    assert api.client.portal
    api.client.portal.call(scenario)

    assert state(api, conv)[0] == ("interrupted", "client_disconnected")
    assert leases(api, actor) == 0
