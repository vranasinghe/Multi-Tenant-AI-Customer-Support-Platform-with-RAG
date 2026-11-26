"""AUD-05 capacity repetitions: the unchanged strict chat capacity file, N times, all results kept.

Usage (repository root):
    python docs/mvp-improvement/tools/perf_a5.py <series> <runs> <qa.env> [--ingestion-load]

Gates live in the test file and are not touched. The series refuses to overwrite itself.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[3]
series, runs, env_file = sys.argv[1], int(sys.argv[2]), sys.argv[3]
mixed = "--ingestion-load" in sys.argv
out = root / "docs/mvp-improvement/evidence/AUD-05/perf" / series
out.mkdir(parents=True, exist_ok=False)
compose = ["docker", "compose", "-p", "acs-a5-qa", "--env-file", env_file]
environment = {**os.environ, "MSYS_NO_PATHCONV": "1"}


def run(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environment, **kwargs,
    )


def host_cpu_percent() -> float | None:
    result = run(
        "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe", "-NoProfile", "-Command",
        "(Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average",
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


load = None
if mixed:
    for source, name in (("live_a5.py", "live_a5.py"), ("measure_a5.py", "measure_a5.py")):
        run(*compose, "cp", f"docs/mvp-improvement/tools/{source}", f"api:/tmp/{name}")
    run(*compose, "exec", "-T", "api", "rm", "-f", "/tmp/a5-load-stop", "/tmp/a5-load-started")
    load = subprocess.Popen(
        [*compose, "exec", "-T", "api", "python", "-"],
        cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=(root / "docs/mvp-improvement/tools/load_a5.py").open("rb"),
    )
    for _ in range(60):
        if run(*compose, "exec", "-T", "api", "test", "-f", "/tmp/a5-load-started").returncode == 0:
            break
        time.sleep(1)
    time.sleep(8)

records = []
for number in range(1, runs + 1):
    cpu = host_cpu_percent()
    stats = run("docker", "stats", "--no-stream", "--format", "{{.Name}} {{.CPUPerc}} {{.MemUsage}}")
    inside = f"/tmp/a5/perf/{series}-{number}"
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
        "containers_before": stats.stdout.strip().splitlines(),
        "summary": result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "",
    }
    for stage in (1, 10, 50, 100):
        path = out / f"run-{number}" / f"capacity-{stage}.json"
        if path.is_file():
            record[f"capacity_{stage}"] = json.loads(path.read_text(encoding="utf-8"))
    records.append(record)
    print(json.dumps({k: record[k] for k in ("run", "exit_code", "summary")}), flush=True)

load_report = None
if load is not None:
    run(*compose, "exec", "-T", "api", "touch", "/tmp/a5-load-stop")
    output = load.communicate(timeout=240)[0].decode("utf-8", errors="replace")
    (out / "load.log").write_text(output, encoding="utf-8")
    lines = [line for line in output.splitlines() if line.startswith("LOAD ")]
    load_report = json.loads(lines[-1][5:]) if lines else {"error": output[-500:]}

summary = {
    "series": series,
    "planned_runs": runs,
    "completed_runs": len(records),
    "failed_runs": sum(r["exit_code"] != 0 for r in records),
    "ingestion_load": load_report,
    "runs": records,
}
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps({k: summary[k] for k in ("completed_runs", "failed_runs", "ingestion_load")}))
