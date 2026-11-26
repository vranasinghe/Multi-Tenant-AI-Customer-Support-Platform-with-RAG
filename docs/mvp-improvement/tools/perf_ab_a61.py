"""A6.1 A/B: the unchanged strict capacity file, alternating the current source ("after") with
saved earlier versions of some files ("before"). Every run is kept.

Usage (repository root):
    python docs/mvp-improvement/tools/perf_ab_a61.py <series> <pairs> <project> <env file> \
        <repo path>=<saved earlier version> [...]

The working files are restored and hash-checked at the end.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
series, pairs, project, env_file = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
out = root / "docs/mvp-improvement/evidence/PERF-01-A6/series" / series
out.mkdir(parents=True, exist_ok=False)
compose = ["docker", "compose", "-p", project, "--env-file", env_file]
environment = {**os.environ, "MSYS_NO_PATHCONV": "1"}
swaps = dict(item.split("=", 1) for item in sys.argv[5:])
after = {name: (root / name).read_bytes() for name in swaps}
before = {name: Path(saved).read_bytes() for name, saved in swaps.items()}


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment,
    )


records = []
try:
    for pair in range(1, pairs + 1):
        order = (("after", after), ("before", before)) if pair % 2 else (
            ("before", before), ("after", after))
        for variant, contents in order:
            for name, data in contents.items():
                (root / name).write_bytes(data)
            inside = f"/tmp/a61/{series}/{variant}-{pair}"
            result = run(
                *compose, "exec", "-T", "-e", f"AUDIT_OUTPUT_DIR={inside}", "api", "pytest",
                "tests/integration/api/mvp_improvement/test_chat_capacity.py",
                "-q", "--tb=short", "-p", "no:cacheprovider",
            )
            run(*compose, "cp", f"api:{inside}", str(out / f"{variant}-{pair}"))
            (out / f"{variant}-{pair}.log").write_text(result.stdout + result.stderr, "utf-8")
            data = json.loads((out / f"{variant}-{pair}/capacity-100.json").read_text())
            record = {
                "pair": pair,
                "variant": variant,
                "exit_code": result.returncode,
                "success_p95_ms": round(data["successful_p95_ms"], 1),
                "rejected_p95_ms": round(data["rejected_p95_ms"], 1),
                "success": data["success"],
                "throughput_rps": round(data["successful_requests_per_second"], 1),
            }
            records.append(record)
            print(json.dumps(record), flush=True)
finally:
    for name, data in after.items():
        (root / name).write_bytes(data)

summary = {
    "series": series,
    "files_swapped": list(swaps),
    "working_files_restored": all(
        hashlib.sha256((root / n).read_bytes()).digest() == hashlib.sha256(d).digest()
        for n, d in after.items()
    ),
    "runs": records,
}
for variant in ("after", "before"):
    chosen = [r for r in records if r["variant"] == variant]
    values = sorted(r["success_p95_ms"] for r in chosen)
    summary[variant] = {
        "p95_values": values,
        "p95_median": values[len(values) // 2],
        "success_median": sorted(r["success"] for r in chosen)[len(chosen) // 2],
        "failed_runs": sum(r["exit_code"] != 0 for r in chosen),
    }
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}))
