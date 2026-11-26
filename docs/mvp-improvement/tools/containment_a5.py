"""Record child PIDs, exit reasons, timings and cleanup for the bounded containment fixtures.

Run inside the QA worker container:  docker compose ... exec -T worker python - < this file
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import structlog

from app.rag import parser_runner
from app.rag.errors import IngestionError
from app.rag.extract import Limits
from app.rag.parser_runner import ParserLimits, ParserRunner

MIB = 1024 * 1024
CASES = {
    "wall 0.5 s against a 5 s parser": ("sleep:5", {"wall_seconds": 0.5}),
    "cpu 1 s against a spinning parser": ("spin", {"cpu_seconds": 1, "wall_seconds": 30}),
    "memory 256 MiB against 384 MiB": ("allocate", {"memory_bytes": 256 * MIB}),
    "result 64 KiB against more": ("oversize", {"max_result_bytes": 64 * 1024}),
}


def children() -> list[int]:
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(fields[1]) == os.getpid():
                found.append(int(entry.name))
    return found


files_before = set(os.listdir(tempfile.gettempdir()))
for name, (mode, limits) in CASES.items():
    runner = ParserRunner(
        ParserLimits(**limits), command=("-m", "tests.support.hostile_parser", mode)
    )
    started = time.monotonic()
    with structlog.testing.capture_logs() as logs:
        parser_runner.log = structlog.get_logger("containment")
        try:
            runner.document(b"fixture", "text/plain", Limits())
            outcome = "parsed"
        except IngestionError as exc:
            outcome = exc.code
    event = next(e for e in logs if e["event"] == "parser.finished")
    row = {"case": name, "code": outcome, "total_seconds": round(time.monotonic() - started, 3)}
    row |= {k: v for k, v in event.items() if k not in {"event", "log_level"}}
    row["children_left"] = children()
    sys.stdout.write("CASE " + json.dumps(row) + "\n")
sys.stdout.write(
    "TEMP " + json.dumps(sorted(set(os.listdir(tempfile.gettempdir())) - files_before)) + "\n"
)
