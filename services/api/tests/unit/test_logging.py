from __future__ import annotations

import json
import logging

import pytest
import structlog

from app.core.logging import configure_logging, get_logger


def _json_lines(out: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in out.splitlines() if line.startswith("{")]


def test_json_logs_include_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    structlog.contextvars.bind_contextvars(request_id="ctx-12345")
    try:
        get_logger("tests.logging").info("hello.world", answer=42)
    finally:
        structlog.contextvars.clear_contextvars()

    entry = _json_lines(capsys.readouterr().out)[-1]
    assert entry["event"] == "hello.world"
    assert entry["answer"] == 42
    assert entry["request_id"] == "ctx-12345"
    assert entry["level"] == "info"
    assert entry["logger"] == "tests.logging"
    assert str(entry["timestamp"]).endswith("Z")


def test_stdlib_library_logs_use_the_same_format(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")

    logging.getLogger("some.library").warning("library says %s", "hi")

    entry = _json_lines(capsys.readouterr().out)[-1]
    assert entry["event"] == "library says hi"
    assert entry["level"] == "warning"


def test_level_filtering(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", "json")

    get_logger("tests.logging").info("hidden")
    get_logger("tests.logging").warning("shown")

    events = [line["event"] for line in _json_lines(capsys.readouterr().out)]
    assert "hidden" not in events
    assert "shown" in events
