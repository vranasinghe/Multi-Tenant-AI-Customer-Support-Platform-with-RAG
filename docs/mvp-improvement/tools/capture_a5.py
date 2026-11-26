"""Capture AUD-05 validation under evidence/AUD-05/. An existing id is never overwritten.

Usage (repository root):  python docs/mvp-improvement/tools/capture_a5.py <id> "<bash>"
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(errors="replace")
root = Path(__file__).resolve().parents[3]
name, command = sys.argv[1:3]
out = root / "docs/mvp-improvement/evidence/AUD-05"
(out / name).parent.mkdir(parents=True, exist_ok=True)
if (out / (name + ".json")).exists():
    sys.exit(f"evidence id {name!r} already exists; choose a new id")

git_bash = Path(r"C:\Program Files\Git\bin\bash.exe")
bash = str(git_bash) if git_bash.is_file() else shutil.which("bash")
started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
started = time.perf_counter()
p = subprocess.run(
    [bash, "-c", "set -o pipefail; " + command],
    cwd=root,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env={**os.environ, "MSYS_NO_PATHCONV": "1"},
)
data = p.stdout + "\n" + p.stderr
data = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", data)
data = re.sub(r"((?:postgres(?:ql)?(?:\+psycopg)?|redis)://[^:/\s]*:)[^@\s]+@", r"\1[REDACTED]@", data)
data = re.sub(r"(?i)(Bearer |__Host-session=)[A-Za-z0-9_.-]+", r"\1[REDACTED]", data)
(out / (name + ".log")).write_text(data, encoding="utf-8")
record = dict(
    id=name,
    command=command,
    started_at=started_at,
    exit_code=p.returncode,
    duration_seconds=round(time.perf_counter() - started, 3),
    log=name + ".log",
)
(out / (name + ".json")).write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps({k: record[k] for k in ("id", "exit_code", "duration_seconds")}))
print(data[-3000:])
sys.exit(p.returncode)
