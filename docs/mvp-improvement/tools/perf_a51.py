"""A5.1 capacity repetitions: the unchanged strict chat capacity file, N times, all results kept.

Usage (repository root):
    python docs/mvp-improvement/tools/perf_a51.py <series> <runs> <qa.env> [--crawl-load]

Gates live in the test file and are not touched. A series never overwrites an earlier one.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[3]
series, runs, env_file = sys.argv[1], int(sys.argv[2]), sys.argv[3]
mixed = "--crawl-load" in sys.argv
out = root / "docs/mvp-improvement/evidence/A5.1/perf" / series
out.mkdir(parents=True, exist_ok=False)
compose = ["docker", "compose", "-p", "acs-a51-qa", "--env-file", env_file]
environment = {**os.environ, "MSYS_NO_PATHCONV": "1"}
POWERSHELL = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
LOAD_COPY = root / "services/api/tests/integration/api/mvp_improvement/test_zz_crawl_load.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment,
    )


def host_cpu_percent() -> float | None:
    result = run(
        POWERSHELL, "-NoProfile", "-Command",
        "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average",
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


load = None
load_report: object = None
try:
    if mixed:
        run(*compose, "exec", "-T", "api", "rm", "-f", "/tmp/a51-load-stop", "/tmp/a51-load-started")
        shutil.copyfile(root / "docs/mvp-improvement/tools/load_crawl_a51.py", LOAD_COPY)
        load_log = (out / "load.log").open("w", encoding="utf-8")
        load = subprocess.Popen(
            [*compose, "exec", "-T", "api", "pytest",
             "tests/integration/api/mvp_improvement/test_zz_crawl_load.py",
             "-q", "-s", "--tb=short", "-p", "no:cacheprovider"],
            cwd=root, env=environment, stdout=load_log, stderr=subprocess.STDOUT,
        )
        for _ in range(90):
            if run(*compose, "exec", "-T", "api", "test", "-f", "/tmp/a51-load-started").returncode == 0:
                break
            if load.poll() is not None:
                sys.exit("the load stopped before it started; see load.log")
            time.sleep(1)
        else:
            sys.exit("the load did not start")
        time.sleep(8)

    records = []
    for number in range(1, runs + 1):
        cpu = host_cpu_percent()
        stats = run("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}")
        inside = f"/tmp/a51/perf/{series}-{number}"
        started = time.monotonic()
        result = run(
            *compose, "exec", "-T", "-e", f"AUDIT_OUTPUT_DIR={inside}", "api", "pytest",
            "tests/integration/api/mvp_improvement/test_chat_capacity.py",
            "-q", "--tb=short", "-p", "no:cacheprovider",
        )
        run(*compose, "cp", f"api:{inside}", str(out / f"run-{number}"))
        (out / f"run-{number}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        record: dict[str, object] = {
            "run": number,
            "exit_code": result.returncode,
            "duration_seconds": round(time.monotonic() - started, 1),
            "host_cpu_percent_before": cpu,
            "load_still_running": None if load is None else load.poll() is None,
            "containers_before": stats.stdout.strip().splitlines(),
            "summary": result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "",
        }
        for stage in (1, 10, 50, 100):
            path = out / f"run-{number}" / f"capacity-{stage}.json"
            if path.is_file():
                record[f"capacity_{stage}"] = json.loads(path.read_text(encoding="utf-8"))
        records.append(record)
        print(json.dumps({k: record[k] for k in ("run", "exit_code", "summary")}), flush=True)

    if load is not None:
        run(*compose, "exec", "-T", "api", "touch", "/tmp/a51-load-stop")
        code = load.wait(timeout=240)
        load_log.close()
        output = (out / "load.log").read_text(encoding="utf-8", errors="replace")
        lines = [line[line.index("LOAD ") + 5:] for line in output.splitlines() if "LOAD {" in line]
        load_report = {"exit_code": code, **(json.loads(lines[-1]) if lines else {})}
finally:
    if load is not None and load.poll() is None:
        run(*compose, "exec", "-T", "api", "touch", "/tmp/a51-load-stop")
        load.wait(timeout=240)
    LOAD_COPY.unlink(missing_ok=True)

p95 = sorted(
    r["capacity_100"]["successful_p95_ms"] for r in records if "capacity_100" in r  # type: ignore[index]
)
summary = {
    "series": series,
    "planned_runs": runs,
    "completed_runs": len(records),
    "failed_runs": sum(r["exit_code"] != 0 for r in records),
    "c100_successful_p95_ms": {"values": p95, "median": p95[len(p95) // 2] if p95 else None},
    "crawl_load": load_report,
    "runs": records,
}
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}))
