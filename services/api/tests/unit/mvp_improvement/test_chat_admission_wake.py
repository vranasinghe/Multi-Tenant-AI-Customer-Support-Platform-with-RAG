"""PERF-01 (A6.1): a released slot is handed to a waiter without waiting for its next poll."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from app.core.errors import ApiError
from app.services import chat_controls
from tests.conftest import make_settings

ORG = uuid.uuid4()


class FakeRedis:
    async def eval(self, *_: Any) -> int:
        return 1


class Slots:
    """`free` slots for the organization; every attempt is recorded."""

    def __init__(self, free: int = 0) -> None:
        self.free = free
        self.attempts = 0

    async def acquire(self, *_: Any) -> str:
        self.attempts += 1
        if self.free > 0:
            self.free -= 1
            return "lease"
        raise ApiError(429, "chat_busy", "busy")

    async def release(self) -> None:
        self.free += 1
        await chat_controls.Lease(chat_controls.org_key(ORG), "c", "t").release(
            cast(Redis, FakeRedis())
        )


@pytest.fixture
def slots(monkeypatch: pytest.MonkeyPatch) -> Slots:
    fake = Slots()
    monkeypatch.setattr(chat_controls, "acquire", fake.acquire)
    return fake


def waiter(wait: float = 0.9) -> asyncio.Task[Any]:
    settings = make_settings(chat_admission_wait_seconds=wait)
    return asyncio.create_task(chat_controls.admit(cast(Redis, None), ORG, uuid.uuid4(), settings))


def waiting() -> int:
    return len(chat_controls._waiting.get(chat_controls.org_key(ORG), ()))


async def test_a_release_hands_the_slot_over_at_once(slots: Slots) -> None:
    task = waiter()
    await asyncio.sleep(0.45)  # well into the long fallback interval
    loop = asyncio.get_running_loop()
    freed = loop.time()

    await slots.release()
    assert await task == "lease"

    assert loop.time() - freed < 0.03
    assert waiting() == 0


async def test_one_release_wakes_one_waiter_in_order(slots: Slots) -> None:
    first, second, third = waiter(), waiter(), waiter()
    await asyncio.sleep(0.45)
    before = slots.attempts

    await slots.release()
    await asyncio.sleep(0.02)

    assert first.done() and not second.done() and not third.done()
    assert slots.attempts - before == 1
    await slots.release()
    await slots.release()
    await asyncio.sleep(0.02)
    assert second.done() and third.done() and waiting() == 0


async def test_a_waiting_request_asks_rarely_when_nothing_is_released(slots: Slots) -> None:
    with pytest.raises(ApiError, match="chat_busy"):
        await waiter()

    assert slots.attempts <= 10, slots.attempts
    assert waiting() == 0


async def test_a_cancelled_waiter_passes_its_wake_on(slots: Slots) -> None:
    first, second = waiter(), waiter()
    await asyncio.sleep(0.45)
    slots.free = 1
    chat_controls.wake(chat_controls.org_key(ORG))  # the first is woken ...
    first.cancel()  # ... and cancelled before it can ask

    with pytest.raises(asyncio.CancelledError):
        await first
    await asyncio.sleep(0.03)

    assert second.done() and second.result() == "lease"
    assert waiting() == 0


async def test_a_release_with_no_waiter_leaves_nothing_behind(slots: Slots) -> None:
    await slots.release()

    assert chat_controls.org_key(ORG) not in chat_controls._waiting
