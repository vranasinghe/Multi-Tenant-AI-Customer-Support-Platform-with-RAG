"""Push once past each worker container limit, in the disposable QA worker only.

Each probe is bounded on its own: at most 2.25 GiB is allocated, 4 processes spin for 3 seconds and
at most 150 short sleeps are started. Run:  docker compose ... exec -T worker python - < this file
"""

import json
import subprocess
import sys
import time
from pathlib import Path

CGROUP = Path("/sys/fs/cgroup")


def stat(name: str) -> dict[str, int]:
    return {k: int(v) for k, v in (line.split() for line in (CGROUP / name).read_text().split("\n") if line)}


out: dict[str, object] = {}

# CPU: four busy processes for three seconds may use at most two CPUs' worth.
before = stat("cpu.stat")
spin = "import time\nend = time.monotonic() + 3\nwhile time.monotonic() < end: pass"
for child in [subprocess.Popen([sys.executable, "-c", spin]) for _ in range(4)]:
    child.wait()
after = stat("cpu.stat")
out["cpu"] = {
    "busy_processes": 4,
    "wall_seconds": 3,
    "cpu_seconds_used": round((after["usage_usec"] - before["usage_usec"]) / 1e6, 2),
    "throttled_periods": after["nr_throttled"] - before["nr_throttled"],
}

# PIDs: starting processes must fail before 150.
children: list[subprocess.Popen[bytes]] = []
error = None
try:
    for _ in range(150):
        children.append(subprocess.Popen(["sleep", "5"]))
except OSError as exc:
    error = f"{type(exc).__name__}: errno {exc.errno}"
out["pids"] = {"started_before_refusal": len(children), "refusal": error}
for child in children:
    child.kill()
    child.wait()

# Memory: one process asking for more than the container has is killed by the kernel.
events = stat("memory.events")
hog = "held = [b'x' * (256 * 1024 * 1024) for _ in range(9)]"  # 2.25 GiB at most, written
result = subprocess.run([sys.executable, "-c", hog], capture_output=True, check=False)
time.sleep(0.5)
out["memory"] = {
    "requested_bytes": 9 * 256 * 1024 * 1024,
    "returncode": result.returncode,
    "oom_kills": stat("memory.events")["oom_kill"] - events["oom_kill"],
}
sys.stdout.write(json.dumps(out, indent=2) + "\n")
