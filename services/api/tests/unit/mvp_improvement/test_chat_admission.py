"""PERF-01: waiting for a chat slot must not busy-poll Redis, and must keep its contract.

Polling every 10 ms made each waiting request issue dozens of Redis scripts on the one event
loop that also serves every admitted request. The wait window, the concurrency cap and the
error stay as they were; only how often a waiter asks again changes.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import pytest
from redis.asyncio import Redis

from app.core.errors import ApiError
from app.services import chat_controls
from tests.conftest import make_settings


class Slots:
    """Stands in for the Redis script: busy until `free_at` seconds after the first attempt."""

    def __init__(self, free_at: float | None = None, error: ApiError | None = None) -> None:
        self.free_at = free_at
        self.error = error
        self.started: float | None = None
        self.attempts: list[float] = []  # seconds since the first attempt

    async def acquire(self, *_: Any) -> str:
        now = asyncio.get_running_loop().time()
        if self.started is None:
            self.started = now
        self.attempts.append(now - self.started)
        if self.error:
            raise self.error
        if self.free_at is not None and self.attempts[-1] >= self.free_at:
            return "lease"
        raise ApiError(429, "chat_busy", "busy")

    @property
    def last(self) -> float:
        return self.attempts[-1]


async def admit(monkeypatch: pytest.MonkeyPatch, slots: Slots, wait: float) -> Any:
    monkeypatch.setattr(chat_controls, "acquire", slots.acquire)
    settings = make_settings(chat_admission_wait_seconds=wait)
    redis = cast(Redis, None)  # the stand-in never touches it
    return await chat_controls.admit(redis, uuid.uuid4(), uuid.uuid4(), settings)


async def test_a_waiter_does_not_busy_poll_and_still_uses_the_whole_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = Slots()

    with pytest.raises(ApiError) as raised:
        await admit(monkeypatch, slots, 0.9)

    assert raised.value.code == "chat_busy"
    assert len(slots.attempts) <= 22, len(slots.attempts)  # 10 ms polling made about 85
    assert 0.88 <= slots.last <= 1.1, slots.last


async def test_a_freed_slot_is_taken_within_one_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = Slots(free_at=0.3)

    assert await admit(monkeypatch, slots, 0.9) == "lease"
    assert 0.3 <= slots.last <= 0.3 + chat_controls.ADMISSION_POLL_MAX_SECONDS + 0.04


async def test_the_first_retry_stays_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = Slots(free_at=0.001)

    assert await admit(monkeypatch, slots, 0.9) == "lease"
    assert len(slots.attempts) == 2
    assert slots.last <= 0.04, slots.last


async def test_no_wait_means_a_single_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = Slots()

    with pytest.raises(ApiError):
        await admit(monkeypatch, slots, 0)

    assert len(slots.attempts) == 1


async def test_other_failures_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = Slots(error=ApiError(503, "chat_unavailable", "down"))

    with pytest.raises(ApiError) as raised:
        await admit(monkeypatch, slots, 0.9)

    assert raised.value.code == "chat_unavailable"
    assert len(slots.attempts) == 1


async def test_cancelling_a_waiter_stops_its_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = Slots()
    task = asyncio.create_task(admit(monkeypatch, slots, 0.9))
    await asyncio.sleep(0.1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    seen = len(slots.attempts)
    await asyncio.sleep(0.15)

    assert len(slots.attempts) == seen
