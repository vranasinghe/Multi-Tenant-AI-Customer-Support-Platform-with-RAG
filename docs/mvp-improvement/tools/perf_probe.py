"""PERF-01 diagnostic pytest plugin: times the send path from outside, without changing it.

Loaded only for diagnosis (`-p perf_probe` with this file on PYTHONPATH). Records durations,
counts and statement *shapes*; never parameters, prompts, documents or credentials. Its own
overhead makes these timings unsuitable as acceptance evidence.

PERF_PROBE_CPU=1 additionally writes a cProfile of the event-loop thread during the burst.
"""

from __future__ import annotations

import asyncio
import contextvars
import cProfile
import functools
import io
import json
import os
import pstats
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

current: contextvars.ContextVar = contextvars.ContextVar("perf_request", default=None)
burst: dict = {}


def reset() -> None:
    burst.clear()
    burst.update(
        rows=[], active=0, sql=defaultdict(lambda: [0, 0.0]), redis=defaultdict(lambda: [0, 0.0]),
        wall_start=None, cpu_start=None, wall=0.0, cpu=0.0, lag=[], profile=None,
    )


reset()


def add(segment: str, seconds: float) -> None:
    record = current.get()
    if record is not None:
        record["segments"][segment] = record["segments"].get(segment, 0.0) + seconds * 1000
        record["counts"][segment] = record["counts"].get(segment, 0) + 1


def timed(owner, name: str, segment: str) -> None:
    original = getattr(owner, name)
    if asyncio.iscoroutinefunction(original):

        @functools.wraps(original)
        async def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return await original(*args, **kwargs)
            finally:
                add(segment, time.perf_counter() - started)

    else:

        @functools.wraps(original)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                add(segment, time.perf_counter() - started)

    setattr(owner, name, wrapper)


def shape(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip()[:90]


def install() -> None:
    from redis.asyncio import Redis
    from sqlalchemy import event
    from sqlalchemy.engine import Engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.pool import Pool

    from app.api import deps
    from app.core.rate_limit import RateLimiter
    from app.services import conversations as service
    from app.services.chat_work import ChatWork

    timed(deps, "find_active_session", "auth_session_lookup")
    timed(RateLimiter, "check", "rate_limit")
    timed(service, "admit" if hasattr(service, "admit") else "acquire", "redis_admission")
    timed(service, "search", "retrieval")
    timed(service, "authorize_chunks", "authorize_chunks")
    timed(service, "assemble", "assemble_prompt")
    timed(service, "reserve", "usage_reservation")
    timed(ChatWork, "query", "query_embedding")
    timed(service, "prepare", "prepare_total")
    timed(AsyncSession, "commit", "db_commit")
    timed(Pool, "connect", "pool_checkout")

    original_auth = ChatWork.authentication

    @asynccontextmanager
    async def authentication(self):
        started = time.perf_counter()
        async with original_auth(self) as slot:
            add("auth_slot_wait", time.perf_counter() - started)
            yield slot

    ChatWork.authentication = authentication

    original_stream = service.stream

    async def stream(services, turn):
        started = time.perf_counter()
        try:
            async for item in original_stream(services, turn):
                yield item
        finally:
            add("stream_and_finalize", time.perf_counter() - started)

    service.stream = stream

    original_command = Redis.execute_command

    async def execute_command(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return await original_command(self, *args, **kwargs)
        finally:
            if burst["active"]:
                entry = burst["redis"][str(args[0])]
                entry[0] += 1
                entry[1] += (time.perf_counter() - started) * 1000

    Redis.execute_command = execute_command

    @event.listens_for(Engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):
        context._probe_started = time.perf_counter()

    @event.listens_for(Engine, "after_cursor_execute")
    def after(conn, cursor, statement, parameters, context, executemany):
        if burst["active"]:
            elapsed = (time.perf_counter() - context._probe_started) * 1000
            entry = burst["sql"][shape(statement)]
            entry[0] += 1
            entry[1] += elapsed
            add("sql_execute", elapsed / 1000)


async def sample_lag() -> None:
    while burst["active"]:
        before = time.perf_counter()
        await asyncio.sleep(0.005)
        burst["lag"].append((time.perf_counter() - before - 0.005) * 1000)


def wrap_request(module) -> None:
    original = module.request
    if getattr(original, "_probe", False):
        return

    async def request(app, actor, path, **kwargs):
        if not path.endswith("/messages") or kwargs.get("method", "POST") != "POST":
            return await original(app, actor, path, **kwargs)
        if burst["active"] == 0 and burst["wall_start"] is None:
            burst["wall_start"], burst["cpu_start"] = time.perf_counter(), time.thread_time()
            burst["sampler"] = None
            if os.environ.get("PERF_PROBE_CPU") == "1":
                burst["profile"] = cProfile.Profile()
                burst["profile"].enable()
        burst["active"] += 1
        if burst.get("sampler") is None:
            burst["sampler"] = asyncio.create_task(sample_lag())
        record = {"segments": {}, "counts": {}}
        token = current.set(record)
        try:
            result = await original(app, actor, path, **kwargs)
            record.update(status=result["status"], duration_ms=result["duration_ms"])
            burst["rows"].append(record)
            return result
        finally:
            current.reset(token)
            burst["active"] -= 1
            if burst["active"] == 0:
                burst["wall"] = (time.perf_counter() - burst["wall_start"]) * 1000
                burst["cpu"] = (time.thread_time() - burst["cpu_start"]) * 1000
                if burst["profile"]:
                    burst["profile"].disable()

    request._probe = True
    module.request = request


def percentiles(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {}
    pick = lambda p: round(ordered[int((len(ordered) - 1) * p)], 1)
    return {"n": len(ordered), "p50": pick(0.5), "p95": pick(0.95), "max": round(ordered[-1], 1)}


def pytest_configure(config) -> None:
    install()


def pytest_runtest_setup(item) -> None:
    reset()
    if hasattr(item.module, "request") and item.module.__name__.endswith("test_chat_capacity"):
        wrap_request(item.module)


def pytest_runtest_teardown(item) -> None:
    if not burst["rows"]:
        return
    folder = Path(os.environ.get("AUDIT_OUTPUT_DIR", "/tmp/perf-probe"))
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9]+", "-", item.name).strip("-")
    groups = {}
    for label, wanted in (("success", {200}), ("rejected", {429, 503})):
        rows = [r for r in burst["rows"] if r["status"] in wanted]
        segments = sorted({s for r in rows for s in r["segments"]})
        groups[label] = {
            "count": len(rows),
            "duration_ms": percentiles([r["duration_ms"] for r in rows]),
            "segments_ms": {s: percentiles([r["segments"].get(s, 0.0) for r in rows]) for s in segments},
            "calls_per_request": {
                s: round(sum(r["counts"].get(s, 0) for r in rows) / len(rows), 2) for s in segments
            }
            if rows
            else {},
        }
    report = {
        "requests": len(burst["rows"]),
        "burst_wall_ms": round(burst["wall"], 1),
        "event_loop_thread_cpu_ms": round(burst["cpu"], 1),
        "event_loop_lag_ms": percentiles(burst["lag"]),
        "groups": groups,
        "sql": sorted(
            ({"statement": k, "calls": v[0], "total_ms": round(v[1], 1)} for k, v in burst["sql"].items()),
            key=lambda x: -x["total_ms"],
        ),
        "redis": {k: {"calls": v[0], "total_ms": round(v[1], 1)} for k, v in burst["redis"].items()},
    }
    (folder / f"probe-{name}.json").write_text(json.dumps(report, indent=2))
    if burst["profile"]:
        text = io.StringIO()
        stats = pstats.Stats(burst["profile"], stream=text)
        stats.sort_stats("tottime").print_stats(35)
        stats.sort_stats("cumulative").print_stats(60)
        (folder / f"profile-{name}.txt").write_text(text.getvalue())
        burst["profile"].dump_stats(folder / f"profile-{name}.pstats")
