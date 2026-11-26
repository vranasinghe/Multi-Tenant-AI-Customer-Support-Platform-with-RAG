"""A6.1 capacity repetitions of the unchanged strict capacity file. Every run is kept.

Usage (repository root):
    python docs/mvp-improvement/tools/perf_a61.py <series> <runs> <project> <env file> [--crawl-load]

Before each run: host CPU, container usage and a fixed single-thread calibration loop inside the
API container. A series never overwrites an earlier one. Gates live in the test and are untouched.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[3]
series, runs, project, env_file = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
mixed = "--crawl-load" in sys.argv
out = root / "docs/mvp-improvement/evidence/PERF-01-A6/series" / series
out.mkdir(parents=True, exist_ok=False)
compose = ["docker", "compose", "-p", project, "--env-file", env_file]
environment = {**os.environ, "MSYS_NO_PATHCONV": "1"}
POWERSHELL = "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
LOAD_COPY = root / "services/api/tests/integration/api/mvp_improvement/test_zz_crawl_load.py"
CALIBRATION = """
import hashlib, time
out = []
for _ in range(15):
    t = time.perf_counter(); h = b"x" * 1000
    for i in range(60000):
        h = hashlib.sha256(h[:64]).digest() + str(i).encode()
    out.append((time.perf_counter() - t) * 1000)
print(round(sorted(out)[7], 1))
"""


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment, input=stdin,
    )


def number(text: str) -> float | None:
    try:
        return float(text.strip())
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
    for index in range(1, runs + 1):
        host = number(run(POWERSHELL, "-NoProfile", "-Command",
            "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average").stdout)
        stats = run("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}")
        calibration = number(
            run(*compose, "exec", "-T", "api", "python", "-", stdin=CALIBRATION).stdout
        )
        inside = f"/tmp/a61/{series}-{index}"
        started = time.monotonic()
        result = run(
            *compose, "exec", "-T", "-e", f"AUDIT_OUTPUT_DIR={inside}", "api", "pytest",
            "tests/integration/api/mvp_improvement/test_chat_capacity.py",
            "-q", "--tb=short", "-p", "no:cacheprovider",
        )
        run(*compose, "cp", f"api:{inside}", str(out / f"run-{index}"))
        (out / f"run-{index}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        record: dict[str, object] = {
            "run": index,
            "exit_code": result.returncode,
            "duration_seconds": round(time.monotonic() - started, 1),
            "host_cpu_percent_before": host,
            "calibration_ms": calibration,
            "load_still_running": None if load is None else load.poll() is None,
            "containers_before": stats.stdout.strip().splitlines(),
            "summary": result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "",
        }
        for stage in (1, 10, 50, 100):
            path = out / f"run-{index}" / f"capacity-{stage}.json"
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                data.pop("raw", None)
                data.get("pool", {}).pop("samples", None)
                record[f"c{stage}"] = data
        records.append(record)
        top = record.get("c100", {})
        print(json.dumps({
            "run": index, "exit": result.returncode, "calibration_ms": calibration,
            "p95": round(top.get("successful_p95_ms", -1), 1),
            "success": top.get("success"), "rejected": top.get("rejected"),
        }), flush=True)

    if load is not None:
        run(*compose, "exec", "-T", "api", "touch", "/tmp/a51-load-stop")
        code = load.wait(timeout=240)
        load_log.close()
        text = (out / "load.log").read_text(encoding="utf-8", errors="replace")
        lines = [line[line.index("LOAD ") + 5:] for line in text.splitlines() if "LOAD {" in line]
        load_report = {"exit_code": code, **(json.loads(lines[-1]) if lines else {})}
finally:
    if load is not None and load.poll() is None:
        run(*compose, "exec", "-T", "api", "touch", "/tmp/a51-load-stop")
        load.wait(timeout=240)
    LOAD_COPY.unlink(missing_ok=True)

values = sorted(r["c100"]["successful_p95_ms"] for r in records if "c100" in r)  # type: ignore[index]
summary = {
    "series": series,
    "planned_runs": runs,
    "completed_runs": len(records),
    "failed_runs": sum(r["exit_code"] != 0 for r in records),
    "c100_success_p95_ms": {
        "median": round(values[len(values) // 2], 1) if values else None,
        "min": round(values[0], 1) if values else None,
        "max": round(values[-1], 1) if values else None,
        "values": [round(v, 1) for v in values],
    },
    "c100_success": [r["c100"]["success"] for r in records if "c100" in r],  # type: ignore[index]
    "crawl_load": load_report,
    "runs": records,
}
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k != "runs"}))
