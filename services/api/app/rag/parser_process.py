"""The parser child: a fresh interpreter that turns one untrusted file into text blocks.

Started only by ``app.rag.parser_runner``. It imports nothing but the pure extraction code, so it
holds no settings, database, Redis, storage or provider client, and it receives no credentials.

Protocol (framed over the two pipes, no files, no pickle):

1. parent → child: one JSON header line (what to parse and the limits);
2. child → parent: ``READY`` once the limits are in force;
3. parent → child: exactly ``size`` bytes of input;
4. child → parent: one JSON result, then exit.

On Linux the child limits itself *before* it reads the input: CPU seconds, address space, no core
dumps, no file writes, few descriptors, death when the parent thread dies, and a wall-clock alarm
as a backstop. This contains resource use. It is **not** a security sandbox: the child keeps the
worker's user id, filesystem view and network namespace.
"""

from __future__ import annotations

import ctypes
import json
import os
import signal
import sys
from collections.abc import Callable
from typing import Any

from app.rag.errors import IngestionError
from app.rag.extract import Block, Limits, extract_document
from app.rag.html_extract import extract_html

READY = b"READY\n"
MAX_HEADER_BYTES = 64 * 1024
OPEN_FILES = 32
#: The child's own alarm fires this long after the parent's deadline should already have.
ALARM_GRACE_SECONDS = 2.0

_PR_SET_PDEATHSIG = 1
_PR_SET_DUMPABLE = 4
#: Built in advance: after a ``MemoryError`` there may be no memory left to build a reply.
_MEMORY_REPLY = b'{"ok": false, "code": "parse_resource_limit", "detail": "out of memory"}'


def containment_supported() -> bool:
    """Whether kernel limits and the parent-death signal are available (Linux only)."""
    return sys.platform == "linux"


def _contain(request: dict[str, Any]) -> None:
    import resource  # noqa: PLC0415 - not available on Windows

    libc = ctypes.CDLL(None, use_errno=True)
    # Tied to the *thread* that spawned us, which waits for us until we are reaped.
    if libc.prctl(_PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "parent-death signal")
    if os.getppid() != request["parent_pid"]:
        os._exit(1)  # the parent died before the signal was armed
    if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "dumpable")

    cpu = int(request["cpu_seconds"])
    memory = int(request["memory_bytes"])
    for kind, wanted_soft, wanted_hard in (
        (resource.RLIMIT_CPU, cpu, cpu + 1),  # SIGXCPU at the soft limit, SIGKILL at the hard
        (resource.RLIMIT_AS, memory, memory),
        (resource.RLIMIT_CORE, 0, 0),
        (resource.RLIMIT_FSIZE, 0, 0),
        (resource.RLIMIT_NOFILE, OPEN_FILES, OPEN_FILES),
    ):
        ceiling = resource.getrlimit(kind)[1]
        soft, hard = wanted_soft, wanted_hard
        if ceiling != resource.RLIM_INFINITY:  # only ever tighten what the container allows
            soft, hard = min(soft, ceiling), min(hard, ceiling)
        resource.setrlimit(kind, (soft, hard))


def _blocks(blocks: list[Block]) -> dict[str, Any]:
    """Blocks with their heading paths interned: many blocks share one long path."""
    paths: dict[tuple[str, ...], int] = {}
    rows = [
        [b.text, b.page, paths.setdefault(b.heading_path, len(paths)), b.is_heading] for b in blocks
    ]
    return {"paths": [list(path) for path in paths], "blocks": rows}


def parse(request: dict[str, Any], data: bytes) -> dict[str, Any]:
    """Run the pure extractor named by the header. Raises ``IngestionError``."""
    if request["kind"] == "html":
        try:
            markup = data.decode(request["charset"], errors="replace")
        except (LookupError, UnicodeError) as exc:
            raise IngestionError("corrupt", type(exc).__name__) from exc
        page = extract_html(markup, request["base_url"])
        return {
            "title": page.title,
            "links": page.links,
            "canonical": page.canonical,
            "noindex": page.noindex,
            "nofollow": page.nofollow,
            **_blocks(page.blocks),
        }
    document = extract_document(data, request["mime_type"], Limits(**request["limits"]))
    return {"title": document.title, "page_count": document.page_count, **_blocks(document.blocks)}


def _failure(code: str, detail: str | None = None) -> bytes:
    return json.dumps({"ok": False, "code": code, "detail": detail}).encode()


def _write(payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        view = view[os.write(1, view) :]


def serve(handler: Callable[[dict[str, Any], bytes], dict[str, Any]]) -> None:
    """Apply the limits, then answer one request. Only safe codes leave this process."""
    stdin = sys.stdin.buffer
    request = json.loads(stdin.readline(MAX_HEADER_BYTES))
    try:
        if containment_supported():
            _contain(request)
        elif request["require_containment"]:
            _write(_failure("containment_unavailable"))
            return
    except (OSError, ValueError):
        _write(_failure("containment_unavailable"))
        return
    _write(READY)
    if hasattr(signal, "setitimer"):
        # Default action of SIGALRM is to terminate: a backstop if the parent cannot act.
        signal.setitimer(signal.ITIMER_REAL, request["wall_seconds"] + ALARM_GRACE_SECONDS)
    try:
        data = stdin.read(request["size"])
        result = {"ok": True, "result": handler(request, data)}
        # surrogatepass keeps whatever the extractor produced; the parent decodes the same way.
        reply = json.dumps(result, ensure_ascii=False).encode("utf-8", "surrogatepass")
    except IngestionError as exc:
        reply = _failure(exc.code, exc.detail)
    except MemoryError:
        reply = _MEMORY_REPLY
    except Exception as exc:  # report the type only: messages can quote the document
        reply = _failure("internal_error", type(exc).__name__)
    _write(reply)


def main() -> None:
    serve(parse)


if __name__ == "__main__":
    main()
