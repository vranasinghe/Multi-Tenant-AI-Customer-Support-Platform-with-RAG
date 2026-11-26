"""AUD-05: document parsing runs in a supervised, resource-limited child process.

Enforcement is real: the hostile fixtures run through the production child harness, so a limit
that is not applied makes the test fail. Containment tests need Linux (the supported production
platform); valid-document and protocol behaviour is checked everywhere.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import structlog

from app.rag import extract, html_extract, parser_process, parser_runner, pipeline
from app.rag.crawler import CrawlConfig, CrawlStats, crawl
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import Limits, extract_document
from app.rag.files import DOCX, PDF, TXT
from app.rag.html_extract import extract_html
from app.rag.parser_runner import ParseCancelledError, ParserLimits, ParserRunner
from tests.support.documents import (
    DOCX_CONTENT_TYPES,
    make_blank_pdf,
    make_docx,
    make_encrypted_pdf,
    make_pdf,
)
from tests.support.site import html_page, serve

linux = pytest.mark.skipif(sys.platform != "linux", reason="containment is enforced on Linux")

MIB = 1024 * 1024
API_ROOT = Path(__file__).resolve().parents[3]


def hostile(mode: str, **limits: Any) -> ParserRunner:
    return ParserRunner(
        ParserLimits(**limits), command=("-m", "tests.support.hostile_parser", mode)
    )


def children(parent: int | None = None) -> dict[int, str]:
    """Direct children of ``parent`` (this process) with their state, from /proc."""
    parent = parent or os.getpid()
    found: dict[int, str] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        state, ppid = stat.rsplit(")", 1)[1].split()[:2]
        if int(ppid) == parent:
            found[int(entry.name)] = state
    return found


def running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in {"Z", "X"}


def wait_until(predicate: Callable[[], Any], timeout: float) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.02)
    pytest.fail("condition not met in time")


def failure(runner: ParserRunner, data: bytes = b"fixture", **kwargs: Any) -> IngestionError:
    with pytest.raises(IngestionError) as info:
        runner.document(data, TXT, Limits(), **kwargs)
    return info.value


def finished_events(logs: list[Any]) -> list[Any]:
    return [entry for entry in logs if entry["event"] == "parser.finished"]


@pytest.fixture
def logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """Captured events from the runner, even after an app has configured (and cached) logging."""
    with structlog.testing.capture_logs() as captured:
        monkeypatch.setattr(parser_runner, "log", structlog.get_logger("parser-test"))
        yield captured


# ------------------------------------------------------------- supported documents unchanged

SUPPORTED = {
    "pdf": (make_pdf(["Alpha shipping policy", "Beta returns policy"]), PDF),
    "docx": (
        make_docx(
            [("h1", "Returns"), ("p", "Thirty days."), ("h2", "EU"), ("tr", "Region|Window")]
        ),
        DOCX,
    ),
    "txt": ("# Title\n\nBody é中 text.\n\n## Part\nMore text.".encode(), TXT),
}


@pytest.mark.parametrize("kind", SUPPORTED)
def test_supported_documents_extract_exactly_as_before(kind: str) -> None:
    data, mime = SUPPORTED[kind]

    isolated = ParserRunner(ParserLimits()).document(data, mime, Limits())

    assert isolated == extract_document(data, mime, Limits())
    assert isolated.blocks


def test_html_extracts_exactly_as_before() -> None:
    body = "<p>Our standard shipping takes three to five business days.</p>" * 6
    data = html_page("Shipping é", body, links=["/a?utm_source=x", "https://other.test/y"])
    url = "https://example.com/shipping"

    page = ParserRunner(ParserLimits()).html(data, url)

    assert page == extract_html(data.decode(), url)
    assert page.links and page.blocks


def test_html_charset_is_honoured_in_the_child() -> None:
    data = "<main><p>Café opening hours are nine to five.</p></main>".encode("cp1252")

    page = ParserRunner(ParserLimits()).html(data, "https://e.com/", "cp1252")

    assert "Café" in page.text


# ------------------------------------------------------------- existing failure codes kept

MALFORMED_INPUTS = {
    "corrupt-pdf": (b"%PDF-1.4\nthis is not really a pdf", PDF, Limits()),
    "encrypted-pdf": (make_encrypted_pdf(), PDF, Limits()),
    "scanned-pdf": (make_blank_pdf(2), PDF, Limits()),
    "page-limit": (make_pdf(["x"] * 4), PDF, Limits(max_pages=3)),
    "text-limit": (make_pdf(["word " * 100]), PDF, Limits(max_chars=100)),
    "empty": (b"", TXT, Limits()),
    "binary-text": (b"abc\x00def", TXT, Limits()),
    "bad-zip": (b"PK\x03\x04 not a zip", DOCX, Limits()),
    "macro-docx": (
        make_docx(
            [("p", "x")],
            content_types=DOCX_CONTENT_TYPES.replace("wordprocessingml.document.main", "ms-word.x"),
        ),
        DOCX,
        Limits(),
    ),
    "zip-expansion": (
        make_docx([("p", "x")], extra={"word/big.bin": b"0" * (4 * MIB)}),
        DOCX,
        Limits(max_uncompressed_bytes=2 * MIB),
    ),
    "unsupported": (b"x", "image/png", Limits()),
}


@pytest.mark.parametrize("name", MALFORMED_INPUTS)
def test_malformed_and_oversized_documents_keep_their_failure_codes(name: str) -> None:
    data, mime, limits = MALFORMED_INPUTS[name]
    with pytest.raises(IngestionError) as expected:
        extract_document(data, mime, limits)

    with pytest.raises(IngestionError) as actual:
        ParserRunner(ParserLimits()).document(data, mime, limits)

    assert actual.value.code == expected.value.code
    assert actual.value.retryable is False


def test_oversized_input_is_refused_before_a_child_is_started() -> None:
    runner = ParserRunner(
        ParserLimits(max_input_bytes=10), command=("-m", "tests.support.does_not_exist")
    )

    assert failure(runner, b"x" * 11).code == "too_large"


# ------------------------------------------------------------- hard limits (Linux)


@linux
def test_the_parent_kills_and_reaps_a_slow_parser_at_the_wall_deadline(logs: list[Any]) -> None:
    error = failure(hostile("sleep:5", wall_seconds=0.5))

    assert error.code == "parse_timeout" and error.retryable is False
    [event] = finished_events(logs)
    assert event["seconds_after_ready"] <= 2.5, event
    assert not running(event["pid"]) and event["pid"] not in children()


@linux
def test_the_child_enforces_its_own_resource_limits() -> None:
    runner = hostile("report-limits", cpu_seconds=7, memory_bytes=256 * MIB)

    reported = json.loads(runner.document(b"x", TXT, Limits()).blocks[0].text)

    assert reported == {
        "RLIMIT_AS": 256 * MIB,
        "RLIMIT_CPU": 7,
        "RLIMIT_CORE": 0,
        "RLIMIT_FSIZE": 0,
        "RLIMIT_NOFILE": 32,
    }


@linux
def test_the_cpu_limit_stops_a_spinning_parser_and_the_parent_survives(logs: list[Any]) -> None:
    error = failure(hostile("spin", cpu_seconds=1, wall_seconds=30))

    assert error.code == "parse_resource_limit" and error.retryable is False
    [event] = finished_events(logs)
    assert event["exit"] == "SIGXCPU", event
    assert event["seconds_after_ready"] < 5
    assert ParserRunner(ParserLimits()).document(b"still working", TXT, Limits()).blocks


@linux
def test_the_memory_limit_stops_an_allocating_parser_and_the_parent_survives() -> None:
    error = failure(hostile("allocate", memory_bytes=256 * MIB))

    assert error.code == "parse_resource_limit", error
    assert error.retryable is False
    assert ParserRunner(ParserLimits()).document(b"still working", TXT, Limits()).blocks


@linux
def test_the_child_cannot_write_document_contents_to_disk(tmp_path: Path) -> None:
    target = tmp_path / "leak.bin"

    error = failure(hostile(f"write-file:{target}"))

    assert error.code in {"parse_resource_limit", "internal_error"}
    assert not target.exists() or target.stat().st_size == 0


@linux
def test_an_oversized_result_is_rejected_without_being_buffered(logs: list[Any]) -> None:
    error = failure(hostile("oversize", max_result_bytes=64 * 1024))

    assert error.code == "parse_resource_limit"
    [event] = finished_events(logs)
    assert event["result_bytes"] <= 64 * 1024 + 1
    assert not running(event["pid"])


@pytest.mark.parametrize(
    "variant",
    [
        "not-json",
        "empty",
        "truncated",
        "wrong-types",
        "bad-path-index",
        "negative-page",
        "unknown-code",
        "not-an-object",
        "deeply-nested",
        "extra-keys-missing",
    ],
)
def test_a_malformed_result_is_rejected(variant: str) -> None:
    error = failure(hostile(f"malformed:{variant}"))

    assert error.code == "parse_invalid_output" and error.retryable is False


def test_the_parent_rechecks_the_text_limit_instead_of_trusting_the_child() -> None:
    with pytest.raises(IngestionError) as info:
        hostile("malformed:too-much-text").document(b"x", TXT, Limits(max_chars=5))

    assert info.value.code == "parse_invalid_output"


@pytest.mark.parametrize("status", [0, 3])
def test_a_child_that_just_exits_is_an_invalid_result(status: int) -> None:
    assert failure(hostile(f"exit:{status}")).code == "parse_invalid_output"


def test_a_parser_that_cannot_start_is_a_transient_failure() -> None:
    runner = ParserRunner(ParserLimits(), command=("-m", "tests.support.does_not_exist"))

    error = failure(runner)

    assert isinstance(error, TransientIngestionError) and error.code == "internal_error"


# ------------------------------------------------------------- lifecycle and cleanup


@linux
def test_cancellation_kills_and_reaps_the_child(logs: list[Any]) -> None:
    started = time.monotonic()

    with pytest.raises(ParseCancelledError):
        hostile("sleep:20").document(
            b"x", TXT, Limits(), cancelled=lambda: time.monotonic() - started > 0.5
        )

    assert time.monotonic() - started < 3
    [event] = finished_events(logs)
    assert not running(event["pid"]) and event["pid"] not in children()


@linux
def test_an_exception_raised_while_waiting_still_reaps_the_child() -> None:
    """A Celery soft time limit arrives as an exception in the waiting thread."""

    class SoftLimitError(Exception):
        pass

    def interrupt() -> bool:
        raise SoftLimitError

    before = set(children())
    with pytest.raises(SoftLimitError):
        hostile("sleep:20").document(b"x", TXT, Limits(), cancelled=interrupt)

    assert set(children()) == before


@linux
def test_no_child_or_temporary_file_survives_success_or_failure() -> None:
    before_children = set(children())
    before_files = set(os.listdir(tempfile.gettempdir()))

    ParserRunner(ParserLimits()).document(b"fine", TXT, Limits())
    failure(hostile("exit:3"))
    failure(hostile("malformed:not-json"))
    failure(hostile("sleep:5", wall_seconds=0.3))

    assert set(children()) == before_children
    assert set(os.listdir(tempfile.gettempdir())) - before_files == set()


@linux
def test_a_hard_killed_parent_leaves_no_running_parser() -> None:
    """`finally` never runs on SIGKILL: the kernel's parent-death signal must clean up."""
    program = (
        "from app.rag.extract import Limits\n"
        "from app.rag.parser_runner import ParserLimits, ParserRunner\n"
        "ParserRunner(ParserLimits(wall_seconds=60), "
        "command=('-m', 'tests.support.hostile_parser', 'sleep:30'))"
        ".document(b'x', 'text/plain', Limits())\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", program], cwd=API_ROOT)  # noqa: S603
    try:
        [parser] = wait_until(lambda: list(children(parent.pid)), 20)
        time.sleep(1)  # let the child get past start-up and into the parse
        assert running(parser)

        parent.kill()
        parent.wait(timeout=5)

        wait_until(lambda: not running(parser), 2)
    finally:
        if parent.poll() is None:
            parent.kill()


# ------------------------------------------------------------- nothing secret goes in or out


@linux
def test_the_child_receives_no_credentials_and_no_inherited_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secrets = {
        "DATABASE_URL": "postgresql+psycopg://app:db-marker-secret@db/x",
        "REDIS_URL": "redis://:redis-marker-secret@redis/0",
        "S3_SECRET_KEY": "s3-marker-secret",
        "LLM_API_KEY": "llm-marker-secret",
        "EMBEDDING_API_KEY": "embedding-marker-secret",
        "SMTP_PASSWORD": "smtp-marker-secret",
        "PYTHONPATH": "/injected-by-test",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    read_end, write_end = os.pipe()
    os.set_inheritable(write_end, True)
    try:
        result = hostile("report-environment").document(b"x", TXT, Limits())
    finally:
        os.close(read_end)
        os.close(write_end)

    report = json.loads(result.blocks[0].text)
    assert set(report["environment"]) <= {"LANG", "LC_CTYPE"}, report["environment"]
    assert not any("marker-secret" in str(v) for v in report.values())
    # stdin, stdout, stderr and the descriptor used to list the directory.
    assert len(report["fds"]) <= 4 and write_end not in report["fds"][:3], report["fds"]


def test_failures_never_log_or_return_document_contents(
    logs: list[Any], capfd: pytest.CaptureFixture[str]
) -> None:
    secret = "PROJECT-NIGHTINGALE-ACQUISITION-41M"

    error = failure(hostile("noisy-crash"), secret.encode())

    assert finished_events(logs), "the failure itself must be logged"

    assert secret not in str(error) and secret not in (error.detail or "")
    assert secret not in json.dumps(logs, default=str)
    captured = capfd.readouterr()
    assert secret not in captured.out + captured.err


# ------------------------------------------------------------- fail closed


def test_required_containment_refuses_to_parse_where_it_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parser_process, "containment_supported", lambda: False)
    runner = ParserRunner(
        ParserLimits(require_containment=True), command=("-m", "tests.support.does_not_exist")
    )

    error = failure(runner)

    assert error.code == "internal_error" and "containment" in (error.detail or "")


# ------------------------------------------------------------- every entry point


def forbid_in_process_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Break the parsers in *this* process only; the child imports them afresh."""

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("parsed inside the long-lived process")

    for name in ("_extract_pdf", "_extract_docx", "_extract_txt"):
        monkeypatch.setattr(extract, name, refuse)
    monkeypatch.setattr(html_extract._Extractor, "feed", refuse)


@pytest.mark.parametrize("kind", [*SUPPORTED, "html"])
def test_stored_originals_are_parsed_only_in_the_child(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    data, mime = SUPPORTED.get(
        kind, (html_page("Stored", "<p>Stored page text.</p>"), pipeline.HTML)
    )
    forbid_in_process_parsing(monkeypatch)

    class Rt:
        limits = Limits()
        parser = ParserRunner(ParserLimits())

    assert pipeline.extract_stored(Rt(), data, mime, "https://example.com/a").blocks  # type: ignore[arg-type]


def test_live_crawl_pages_are_parsed_only_in_the_child(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_in_process_parsing(monkeypatch)
    text = "Our standard shipping takes three to five business days in the country. " * 6
    with serve() as site:
        site.page("/", "Home", f"<p>{text}</p>")

        pages = list(
            crawl(
                site.fetcher(),
                CrawlConfig(site.base + "/", delay_seconds=0),
                CrawlStats(),
                sleep=lambda _s: None,
            )
        )

    assert len(pages) == 1 and "business days" in "\n".join(b.text for b in pages[0].blocks)


def test_a_page_the_parser_cannot_handle_is_counted_and_skipped() -> None:
    text = "Our standard shipping takes three to five business days in the country. " * 6
    runner = ParserRunner(ParserLimits())

    def parse(data: bytes, charset: str, url: str) -> Any:
        if url.endswith("/bad"):
            raise IngestionError("parse_timeout")
        return runner.html(data, url, charset)

    stats = CrawlStats()
    with serve() as site:
        site.page("/", "Home", f"<p>{text}</p>", links=["/bad", "/good"])
        site.page("/bad", "Bad", f"<p>Bad. {text}</p>")
        site.page("/good", "Good", f"<p>Good. {text}</p>")

        pages = list(
            crawl(
                site.fetcher(),
                CrawlConfig(site.base + "/", delay_seconds=0),
                stats,
                sleep=lambda _s: None,
                parse=parse,
            )
        )

    assert {p.url.removeprefix(site.base) for p in pages} == {"/", "/good"}
    assert stats.errors == 1 and "parse_timeout" in stats.error_samples[0]


def test_runner_defaults_match_the_documented_budgets() -> None:
    limits = ParserLimits()

    assert (limits.wall_seconds, limits.cpu_seconds) == (60, 30)
    assert limits.memory_bytes == 512 * MIB
    assert limits.max_result_bytes == 32 * MIB
    assert parser_runner.KILL_GRACE_SECONDS <= 2
