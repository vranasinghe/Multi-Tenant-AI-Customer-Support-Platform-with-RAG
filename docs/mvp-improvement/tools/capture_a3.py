"""Capture isolated A3 validation; never write original audit artifacts."""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(errors="replace")
root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/AUD-03"
out.mkdir(parents=True, exist_ok=True)
name, command = sys.argv[1:3]
started = time.perf_counter()
p = subprocess.run(
    ["pwsh", "-NoProfile", "-Command", command],
    cwd=root,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
data = p.stdout + "\n" + p.stderr
data = re.sub(
    r"(postgres(?:ql)?(?:\+psycopg)?://[^:/\s]+:)[^@\s]+@", r"\1[REDACTED]@", data
)
data = re.sub(r"(?i)(Bearer |__Host-session=)[A-Za-z0-9_.-]+", r"\1[REDACTED]", data)
(out / (name + ".log")).write_text(data, encoding="utf-8")
record = dict(
    id=name,
    command=command,
    exit_code=p.returncode,
    duration_seconds=round(time.perf_counter() - started, 3),
    log=name + ".log",
)
(out / (name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps(record))
print(data[-2200:])
sys.exit(p.returncode)
