"""Run a predeclared number of independent strict-capacity repetitions and keep every result.

Usage (repository root):
    python docs/mvp-improvement/tools/perf01_series.py <series> <runs> <qa-env-file> "<condition>"

Each repetition is a fresh pytest process running the unchanged capacity file (concurrency
1/10/50/100 plus second-tenant fairness). A series directory is never reused or resumed.
"""

import hashlib
import json
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[3]
series, runs, env_file, condition = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
out = root / "docs/mvp-improvement/evidence/PERF-01/series" / series
if out.exists():
    sys.exit(f"series {series!r} already exists; choose a new name")
out.mkdir(parents=True)
compose = ["docker", "compose", "-p", "acs-a41-qa", "--env-file", env_file]
TEST = "tests/integration/api/mvp_improvement/test_chat_capacity.py"


def sh(args, timeout=600):
    return subprocess.run(args, cwd=root, capture_output=True, text=True, errors="replace", timeout=timeout)


def host_cpu_percent():
    command = "(Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples 3).CounterSamples.CookedValue | Measure-Object -Average | ForEach-Object Average"
    shell = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    result = sh([shell, "-NoProfile", "-Command", command]).stdout.strip()
    return round(float(result.replace(",", ".")), 1) if result else None


def environment():
    return {
        "host_cpu_percent": host_cpu_percent(),
        "containers": sh(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}}"]
        ).stdout.strip().splitlines(),
    }


declaration = {
    "series": series,
    "planned_runs": runs,
    "condition": condition,
    "declared_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "head": sh(["git", "rev-parse", "HEAD"]).stdout.strip(),
    "app_diff_sha256": hashlib.sha256(sh(["git", "diff", "HEAD", "--", "services/api"]).stdout.encode()).hexdigest(),
    "app_diff_stat": sh(["git", "diff", "--stat", "HEAD", "--", "services/api"]).stdout.splitlines(),
}
(out / "declaration.json").write_text(json.dumps(declaration, indent=2), encoding="utf-8")

results = []
for number in range(1, runs + 1):
    run = out / f"{number:02d}"
    run.mkdir()
    inside = f"/tmp/perf01/{series}/{number:02d}"
    record = {"run": number, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "before": environment()}
    p = sh(
        [*compose, "exec", "-T", "-e", f"AUDIT_OUTPUT_DIR={inside}", "api", "pytest", TEST, "-q",
         "--tb=short", "-p", "no:cacheprovider", f"--junitxml={inside}/junit.xml"]
    )
    (run / "pytest.log").write_text(p.stdout + "\n" + p.stderr, encoding="utf-8")
    sh([*compose, "cp", f"api:{inside}/.", str(run)])
    record["exit_code"] = p.returncode
    record["failed_tests"] = [
        c.get("name")
        for c in ElementTree.parse(run / "junit.xml").findall(".//testcase")
        if c.find("failure") is not None or c.find("error") is not None
    ]
    for level in (1, 10, 50, 100):
        report = json.loads((run / f"capacity-{level}.json").read_text())
        record[str(level)] = {
            key: report[key]
            for key in ("success", "rejected", "failed", "successful_p95_ms", "rejected_p95_ms",
                        "overlap_peak", "provider_peak")
        }
        pool = report["pool"]
        record[str(level)]["pool"] = {k: pool[k] for k in ("checked_out", "peak", "checkouts", "checkins")}
    (run / "record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    results.append(record)
    hundred = record["100"]
    print(number, "exit", p.returncode, "c100 p95", round(hundred["successful_p95_ms"], 1),
          f"{hundred['success']}/{hundred['rejected']}/{hundred['failed']}", "cpu", record["before"]["host_cpu_percent"],
          record["failed_tests"], flush=True)

summary = {**declaration, "completed_runs": len(results),
           "failed_runs": sum(r["exit_code"] != 0 for r in results)}
for level in ("1", "10", "50", "100"):
    values = [r[level]["successful_p95_ms"] for r in results]
    summary[f"successful_p95_ms_c{level}"] = {
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "all": [round(v, 2) for v in values],
    }
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
shutil.rmtree(out / "__pycache__", ignore_errors=True)
print(json.dumps({k: summary[k] for k in ("series", "completed_runs", "failed_runs", "successful_p95_ms_c100")}))
