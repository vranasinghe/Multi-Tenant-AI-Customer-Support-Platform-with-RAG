"""Supervised execution of document parsers (AUD-05).

Every PDF, DOCX, TXT and HTML parse goes through ``ParserRunner``: a fresh interpreter
(``parser_process``) with an empty environment, bounded input and output, kernel limits applied by
the child, and a wall-clock deadline enforced here. Whatever happens — success, failure,
cancellation or an exception raised into the waiting thread (a Celery soft time limit) — the
child is killed if still running and reaped before control returns. If this process itself is
killed, the child's parent-death signal ends it.

The child's output is untrusted: it is size-bounded, parsed as JSON and checked field by field.
Its stderr is discarded because a parser traceback can quote the document.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.rag import parser_process
from app.rag.errors import IngestionError, TransientIngestionError
from app.rag.extract import Block, ExtractedDocument, Limits
from app.rag.html_extract import MAX_LINKS, HtmlPage

log = get_logger(__name__)

KILL_GRACE_SECONDS = 2.0
STARTUP_SECONDS = 30.0
_TICK_SECONDS = 0.02
_CODE_ROOT = Path(__file__).resolve().parents[2]  # the directory ``app`` is imported from
#: Nothing else is passed on. Windows cannot start Python without these two.
_ENVIRONMENT = ("SYSTEMROOT", "WINDIR")
#: Codes a child may report. Anything else is treated as a malformed result.
_CHILD_CODES = frozenset(
    {
        "corrupt",
        "encrypted",
        "no_text",
        "too_large",
        "too_many_pages",
        "unsupported_type",
        "parse_resource_limit",
        "internal_error",
    }
)
_SAFE_DETAIL = re.compile(r"[A-Za-z0-9 _./-]{0,120}\Z")


class ParseCancelledError(Exception):
    """The caller no longer wants the result (document deleted or attempt superseded)."""


@dataclass(frozen=True)
class ParserLimits:
    wall_seconds: float = 60.0
    cpu_seconds: int = 30
    memory_bytes: int = 512 * 1024 * 1024
    max_input_bytes: int = 25 * 1024 * 1024 + 1024
    max_result_bytes: int = 32 * 1024 * 1024
    #: Refuse to parse where kernel limits are unavailable (staging and production).
    require_containment: bool = False


class ParserRunner:
    def __init__(
        self,
        limits: ParserLimits,
        *,
        command: tuple[str, ...] = ("-m", "app.rag.parser_process"),
        cancel_poll_seconds: float = 1.0,
    ) -> None:
        self.limits = limits
        self._command = command
        self._cancel_poll = cancel_poll_seconds

    def document(
        self,
        data: bytes,
        mime_type: str,
        limits: Limits,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> ExtractedDocument:
        """Isolated ``extract_document``. Raises ``IngestionError`` or ``ParseCancelledError``."""
        request = {"kind": "document", "mime_type": mime_type, "limits": asdict(limits)}
        result = self._run(request, data, cancelled)
        try:
            page_count = result["page_count"]
            if page_count is not None and (type(page_count) is not int or page_count < 0):
                raise _invalid("page count")
            return ExtractedDocument(
                blocks=_blocks(result, max_chars=limits.max_chars),
                page_count=page_count,
                title=_optional_str(result["title"]),
            )
        except (KeyError, TypeError) as exc:
            raise _invalid(type(exc).__name__) from None

    def html(
        self,
        data: bytes,
        base_url: str,
        charset: str = "utf-8",
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> HtmlPage:
        """Isolated ``extract_html`` of bytes in ``charset``."""
        request = {"kind": "html", "base_url": base_url, "charset": charset}
        result = self._run(request, data, cancelled)
        try:
            links = result["links"]
            if (
                not isinstance(links, list)
                or len(links) > MAX_LINKS
                or not all(isinstance(link, str) for link in links)
                or not isinstance(result["noindex"], bool)
                or not isinstance(result["nofollow"], bool)
            ):
                raise _invalid("page fields")
            return HtmlPage(
                title=_optional_str(result["title"]),
                blocks=_blocks(result, max_chars=None),
                links=links,
                canonical=_optional_str(result["canonical"]),
                noindex=result["noindex"],
                nofollow=result["nofollow"],
            )
        except (KeyError, TypeError) as exc:
            raise _invalid(type(exc).__name__) from None

    # ------------------------------------------------------------------------- supervision

    def _run(
        self, request: dict[str, Any], data: bytes, cancelled: Callable[[], bool] | None
    ) -> dict[str, Any]:
        limits = self.limits
        if len(data) > limits.max_input_bytes:
            raise IngestionError("too_large", "parser input limit")
        if limits.require_containment and not parser_process.containment_supported():
            raise TransientIngestionError("internal_error", "parser containment unavailable")
        header = {
            **request,
            "size": len(data),
            "parent_pid": os.getpid(),
            "wall_seconds": limits.wall_seconds,
            "cpu_seconds": limits.cpu_seconds,
            "memory_bytes": limits.memory_bytes,
            "max_result_bytes": limits.max_result_bytes,
            "require_containment": limits.require_containment,
        }
        try:
            process = subprocess.Popen(  # noqa: S603 - fixed argv; document data never reaches it
                [sys.executable, "-E", "-s", "-B", *self._command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={k: os.environ[k] for k in _ENVIRONMENT if k in os.environ},
                cwd=_CODE_ROOT,
                close_fds=True,
                start_new_session=True,
            )
        except OSError as exc:
            raise TransientIngestionError("internal_error", "parser could not start") from exc

        exchange = _Exchange(process, header, data, limits.max_result_bytes)
        outcome = "completed"
        try:
            outcome = self._wait(exchange, cancelled)
            if outcome == "completed" and len(exchange.output) <= limits.max_result_bytes:
                try:
                    process.wait(timeout=KILL_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    outcome = "did not exit"
        except BaseException:
            outcome = "cancelled"
            raise
        finally:
            _stop(process)
            exchange.close()
            log.info(
                "parser.finished",
                pid=process.pid,
                kind=request["kind"],
                outcome=outcome,
                exit=_exit_reason(process.returncode),
                seconds_after_ready=exchange.seconds_after_ready(),
                result_bytes=len(exchange.output),
                wall_seconds=limits.wall_seconds,
                cpu_seconds=limits.cpu_seconds,
                memory_bytes=limits.memory_bytes,
                contained=parser_process.containment_supported(),
            )
        return self._interpret(process.returncode, outcome, exchange)

    def _wait(self, exchange: _Exchange, cancelled: Callable[[], bool] | None) -> str:
        started = time.monotonic()
        next_poll = started + self._cancel_poll
        while not exchange.done.wait(_TICK_SECONDS):
            now = time.monotonic()
            if exchange.ready_at is None:
                if now - started > STARTUP_SECONDS:
                    return "startup timeout"
            elif now - exchange.ready_at > self.limits.wall_seconds:
                return "wall timeout"
            if cancelled is not None and now >= next_poll:
                if cancelled():
                    raise ParseCancelledError
                next_poll = time.monotonic() + self._cancel_poll
        return "completed"

    def _interpret(self, returncode: int, outcome: str, exchange: _Exchange) -> dict[str, Any]:
        if outcome == "wall timeout":
            raise IngestionError("parse_timeout")
        if outcome == "startup timeout":
            raise TransientIngestionError("internal_error", "parser start-up timed out")
        if len(exchange.output) > self.limits.max_result_bytes:
            raise IngestionError("parse_resource_limit", "result too large")
        reason = _exit_reason(returncode)
        failure = _signal_failure(reason, killed_by_us=outcome != "completed")
        if failure is not None:
            raise failure
        if exchange.ready_at is None and not exchange.output:
            raise TransientIngestionError("internal_error", "parser could not start")
        if returncode != 0:
            raise _invalid(reason)
        try:
            payload = json.loads(exchange.output.decode("utf-8", "surrogatepass"))
        except (ValueError, RecursionError):
            raise _invalid("not JSON") from None
        if not isinstance(payload, dict):
            raise _invalid("not an object")
        if payload.get("ok") is True and isinstance(payload.get("result"), dict):
            result: dict[str, Any] = payload["result"]
            return result
        code = payload.get("code")
        if payload.get("ok") is False and code == "containment_unavailable":
            raise TransientIngestionError("internal_error", "parser containment unavailable")
        if payload.get("ok") is not False or code not in _CHILD_CODES:
            raise _invalid("unknown reply")
        detail = payload.get("detail")
        safe = isinstance(detail, str) and _SAFE_DETAIL.match(detail)
        raise IngestionError(str(code), detail if safe else None)


class _Exchange:
    """Pipe I/O on a helper thread, so the supervising thread can always act on its deadline."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        header: dict[str, Any],
        data: bytes,
        max_result_bytes: int,
    ) -> None:
        self.output = b""
        self.ready_at: float | None = None
        self.done = threading.Event()
        self._finished_at: float | None = None
        self._process = process
        self._thread = threading.Thread(
            target=self._talk, args=(header, data, max_result_bytes), daemon=True
        )
        self._thread.start()

    def _talk(self, header: dict[str, Any], data: bytes, max_result_bytes: int) -> None:
        stdin, stdout = self._process.stdin, self._process.stdout
        assert stdin is not None  # noqa: S101 - opened with PIPE
        assert stdout is not None  # noqa: S101
        try:
            stdin.write(json.dumps(header).encode() + b"\n")
            stdin.flush()
            first = stdout.readline(4096)
            if first == parser_process.READY:
                self.ready_at = time.monotonic()
                first = b""
                try:
                    stdin.write(data)
                    stdin.close()
                except OSError:
                    pass  # the child stopped reading; its exit status says why
            self.output = first + stdout.read(max_result_bytes + 1 - len(first))
        except (OSError, ValueError):
            pass
        finally:
            self._finished_at = time.monotonic()
            self.done.set()

    def seconds_after_ready(self) -> float | None:
        if self.ready_at is None:
            return None
        return round((self._finished_at or time.monotonic()) - self.ready_at, 3)

    def close(self) -> None:
        """Call only after the child is gone: its death is what unblocks the thread."""
        self._thread.join(KILL_GRACE_SECONDS)
        for pipe in (self._process.stdin, self._process.stdout):
            if pipe is not None:
                with contextlib.suppress(OSError):  # unsent input to a dead child
                    pipe.close()


def _stop(process: subprocess.Popen[bytes]) -> None:
    """Kill the child's process group if it is still running, then reap it."""
    if process.poll() is None:
        if sys.platform == "win32":
            process.kill()
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        log.error("parser.not_reaped", pid=process.pid)


def _exit_reason(returncode: int | None) -> str:
    if returncode is None:
        return "running"
    if returncode < 0:
        try:
            return signal.Signals(-returncode).name
        except ValueError:
            return f"signal {-returncode}"
    return f"exit {returncode}"


def _signal_failure(reason: str, *, killed_by_us: bool) -> IngestionError | None:
    if reason == "SIGXCPU":
        return IngestionError("parse_resource_limit", "cpu limit")
    if reason == "SIGALRM":
        return IngestionError("parse_timeout", "child alarm")
    if reason in {"SIGSEGV", "SIGABRT", "SIGBUS"}:
        return IngestionError("parse_resource_limit", "parser crashed")
    if reason == "SIGKILL" and not killed_by_us:
        # Most likely the container's memory killer, so retry (bounded).
        return TransientIngestionError("parse_resource_limit", "parser was killed")
    return None


def _invalid(detail: str) -> IngestionError:
    return IngestionError("parse_invalid_output", detail)


def _optional_str(value: object) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise _invalid("text field")


def _blocks(result: dict[str, Any], *, max_chars: int | None) -> list[Block]:
    paths = result["paths"]
    if not isinstance(paths, list) or not all(
        isinstance(path, list) and all(isinstance(part, str) for part in path) for path in paths
    ):
        raise _invalid("heading paths")
    interned = [tuple(path) for path in paths]
    blocks: list[Block] = []
    total = 0
    rows = result["blocks"]
    if not isinstance(rows, list):
        raise _invalid("blocks")
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise _invalid("block")
        text, page, path, is_heading = row
        if (
            not isinstance(text, str)
            or (page is not None and (type(page) is not int or page < 1))
            or type(path) is not int
            or not 0 <= path < len(interned)
            or not isinstance(is_heading, bool)
        ):
            raise _invalid("block")
        total += len(text)
        if max_chars is not None and total > max_chars:
            raise _invalid("text exceeds the limit")
        blocks.append(
            Block(text=text, page=page, heading_path=interned[path], is_heading=is_heading)
        )
    return blocks
