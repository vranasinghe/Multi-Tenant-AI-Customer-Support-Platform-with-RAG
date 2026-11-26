"""AUD-06 capacity A/B: the unchanged strict capacity file, alternating the AUD-06 backend files
("after") with their original versions from HEAD ("before"). Every run is kept.

Usage (repository root):  python docs/mvp-improvement/tools/perf_ab_a6.py <series> <pairs> <qa.env>

Both original files were unmodified relative to HEAD when AUD-06 began (checked against the
preflight hashes). The working files are restored and hash-checked at the end.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
series, pairs, env_file = sys.argv[1], int(sys.argv[2]), sys.argv[3]
evidence = root / "docs/mvp-improvement/evidence/AUD-06"
out = evidence / "perf" / series
out.mkdir(parents=True, exist_ok=False)
FILES = ["services/api/app/services/inbox.py", "services/api/app/api/conversations.py"]
compose = ["docker", "compose", "-p", "acs-a6-qa", "--env-file", env_file]
environment = {**os.environ, "MSYS_NO_PATHCONV": "1"}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment,
    )


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


recorded = json.loads((evidence / "preflight/before_hashes.json").read_text())
after = {name: (root / name).read_bytes() for name in FILES}
before = {}
for name in FILES:
    blob = subprocess.run(
        ["git", "show", f"HEAD:{name}"], cwd=root, capture_output=True, check=True
    ).stdout
    candidates = [blob, blob.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")]
    before[name] = next(c for c in candidates if digest(c) == recorded[name])

records = []
try:
    for number in range(1, pairs + 1):
        for variant, contents in (("after", after), ("before", before)):
            for name, data in contents.items():
                (root / name).write_bytes(data)
            inside = f"/tmp/a6/{series}/{variant}-{number}"
            result = run(
                *compose, "exec", "-T", "-e", f"AUDIT_OUTPUT_DIR={inside}", "api", "pytest",
                "tests/integration/api/mvp_improvement/test_chat_capacity.py",
                "-q", "--tb=short", "-p", "no:cacheprovider",
            )
            run(*compose, "cp", f"api:{inside}", str(out / f"{variant}-{number}"))
            (out / f"{variant}-{number}.log").write_text(result.stdout + result.stderr, "utf-8")
            stage = json.loads((out / f"{variant}-{number}/capacity-100.json").read_text())
            record = {
                "pair": number,
                "variant": variant,
                "exit_code": result.returncode,
                "success_p95_ms": round(stage["successful_p95_ms"], 1),
                "rejected_p95_ms": round(stage["rejected_p95_ms"], 1),
                "success": stage["success"],
            }
            records.append(record)
            print(json.dumps(record), flush=True)
finally:
    for name, data in after.items():
        (root / name).write_bytes(data)

restored = all(digest((root / n).read_bytes()) == digest(d) for n, d in after.items())
summary = {"series": series, "pairs": pairs, "working_files_restored": restored, "runs": records}
for variant in ("after", "before"):
    values = sorted(r["success_p95_ms"] for r in records if r["variant"] == variant)
    summary[variant] = {
        "values": values,
        "median": values[len(values) // 2],
        "over_2000": sum(v > 2000 for v in values),
        "failed_runs": sum(r["exit_code"] != 0 for r in records if r["variant"] == variant),
    }
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}))
