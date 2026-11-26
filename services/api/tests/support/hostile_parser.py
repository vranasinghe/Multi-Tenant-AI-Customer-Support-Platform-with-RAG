"""Misbehaving parser children for AUD-05 tests, run through the *real* child harness.

``python -m tests.support.hostile_parser <mode>`` applies exactly the limits the production child
applies (``parser_process.serve``) and then misbehaves. Every behaviour is also bounded here, so a
missing limit makes a test fail instead of exhausting the machine: at most 384 MiB is allocated,
at most 10 CPU-seconds are burned and sleeps end on their own.

Mode ``by-content`` behaves normally unless the document starts with ``HOSTILE:<mode>[:<arg>]``,
which lets one real worker serve both the slow tenant and the healthy one. A web page asks for the
same with an ``<!--HOSTILE:<mode>[:<arg>]-->`` comment.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from app.rag import parser_process

MIB = 1024 * 1024
PAGE_REQUEST = re.compile(rb"<!--HOSTILE:(.+?)-->")


def _sleep(seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        time.sleep(0.05)


def _spin() -> None:
    while time.process_time() < 10:
        pass


def _allocate() -> None:
    held = []
    for _ in range(24):  # 384 MiB at most
        held.append(bytearray(16 * MIB))


def _raw(payload: bytes) -> None:
    os.write(1, payload)
    os._exit(0)


def _document(text: str) -> dict[str, Any]:
    return {"title": None, "page_count": None, "paths": [[]], "blocks": [[text, None, 0, False]]}


MALFORMED: dict[str, bytes] = {
    "not-json": b"this is not a result",
    "empty": b"",
    "truncated": b'{"ok": true, "result": {"blocks": [',
    "wrong-types": json.dumps(
        {"ok": True, "result": {**_document("x"), "blocks": [[1, "2", "3", "no"]]}}
    ).encode(),
    "bad-path-index": json.dumps(
        {"ok": True, "result": {**_document("x"), "blocks": [["x", None, 7, False]]}}
    ).encode(),
    "negative-page": json.dumps(
        {"ok": True, "result": {**_document("x"), "blocks": [["x", -1, 0, False]]}}
    ).encode(),
    "unknown-code": json.dumps({"ok": False, "code": "rm -rf /", "detail": "x"}).encode(),
    "not-an-object": b"[1, 2, 3]",
    "deeply-nested": b"[" * 200_000,
    "extra-keys-missing": json.dumps({"ok": True}).encode(),
    "too-much-text": json.dumps({"ok": True, "result": _document("twelve chars")}).encode(),
}


def behave(mode: str, request: dict[str, Any], data: bytes) -> dict[str, Any]:
    name, _, argument = mode.partition(":")
    if name == "sleep":
        _sleep(float(argument or 5))
    elif name == "hang-on-call":  # ``<n>:<marker>``: only the n-th parse hangs
        number, _, marker = argument.partition(":")
        if _call_number(marker) == int(number):
            _sleep(60)
    elif name == "spin":
        _spin()
    elif name == "allocate":
        _allocate()
        return _document("the memory limit was NOT enforced")
    elif name == "oversize":
        _raw(b"x" * (int(request["max_result_bytes"]) + 1024))
    elif name == "malformed":
        _raw(MALFORMED[argument])
    elif name == "exit":
        os._exit(int(argument))
    elif name == "report-limits":
        import resource  # POSIX only; the other modes also run on Windows

        limits = {
            key: resource.getrlimit(getattr(resource, key))[0]
            for key in ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_CORE", "RLIMIT_FSIZE", "RLIMIT_NOFILE")
        }
        return _document(json.dumps(limits))
    elif name == "report-environment":
        fds = sorted(int(fd) for fd in os.listdir("/proc/self/fd"))
        return _document(
            json.dumps({"environment": dict(os.environ), "fds": fds, "argv": sys.argv})
        )
    elif name == "write-file":
        with open(argument, "wb") as handle:  # must fail under RLIMIT_FSIZE=0
            handle.write(b"document contents")
    elif name == "noisy-crash":
        sys.stderr.write(data.decode("utf-8", errors="replace"))
        raise RuntimeError(data.decode("utf-8", errors="replace"))
    return parser_process.parse(request, data)


def _call_number(marker: str) -> int:
    """How many parses used this marker, counting this one (empty files; writes are blocked)."""
    number = 1
    while True:
        try:
            os.close(os.open(f"{marker}.{number}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            number += 1
        else:
            return number


def main() -> None:
    mode = sys.argv[1]

    def handler(request: dict[str, Any], data: bytes) -> dict[str, Any]:
        if mode != "by-content":
            return behave(mode, request, data)
        if data.startswith(b"HOSTILE:"):
            first_line = data.split(b"\n", 1)[0].decode().strip()
            return behave(first_line.removeprefix("HOSTILE:"), request, data)
        if asked := PAGE_REQUEST.search(data):
            return behave(asked[1].decode(), request, data)
        return parser_process.parse(request, data)

    parser_process.serve(handler)


if __name__ == "__main__":
    main()
