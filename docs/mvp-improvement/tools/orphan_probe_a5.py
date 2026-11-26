"""Kill a process that is waiting on a parser, then look for the orphan (running or zombie).

Run inside a container: docker compose ... exec -T <service> python - < this file. The bounded
parser fixture sleeps at most 30 seconds. Reports PID 1 and the orphan's state afterwards.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

program = (
    "from app.rag.extract import Limits\n"
    "from app.rag.parser_runner import ParserLimits, ParserRunner\n"
    "ParserRunner(ParserLimits(), command=('-m','tests.support.hostile_parser','sleep:30'))"
    ".document(b'x', 'text/plain', Limits())\n"
)
parent = subprocess.Popen([sys.executable, "-c", program], cwd="/app")


def children(pid: int) -> list[int]:
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(fields[1]) == pid:
                found.append(int(entry.name))
    return found


for _ in range(200):
    if children(parent.pid):
        break
    time.sleep(0.05)
[orphan] = children(parent.pid)
time.sleep(1)
parent.kill()
parent.wait()
time.sleep(1)
try:
    state = Path(f"/proc/{orphan}/stat").read_text().rsplit(")", 1)[1].split()[0]
except OSError:
    state = "gone"
pid1 = Path("/proc/1/cmdline").read_bytes().split(b"\x00")[0].decode()
sys.stdout.write(json.dumps({"pid1": pid1, "orphan_state_after_1s": state}) + "\n")
