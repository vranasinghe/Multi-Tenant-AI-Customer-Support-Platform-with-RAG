"""Bounded background ingestion for the mixed ingestion/chat measurement.

Two synthetic tenants keep uploading ~190 KiB text files through the running QA stack until
/tmp/a5-load-stop exists (or ten minutes pass). Run inside the QA api container after
/tmp/live_a5.py and /tmp/measure_a5.py are in place. Reports what was ingested.
"""

import json
import sys
import time
import types
import uuid
from pathlib import Path

source = open("/tmp/live_a5.py", encoding="utf-8").read()  # noqa: SIM115, PTH123
live = types.ModuleType("live_base")
exec(source[: source.index("data, xml = ")], live.__dict__)  # noqa: S102 - account() only

STOP = Path("/tmp/a5-load-stop")
LINE = "Standard shipping to the United States takes three to five business days after dispatch. "

tenants = [live.account(), live.account()]
sent: list[tuple[int, str]] = []
started = time.monotonic()
Path("/tmp/a5-load-started").touch()
number = 0
while not STOP.exists() and time.monotonic() - started < 600:
    for index, (client, headers, path) in enumerate(tenants):
        number += 1
        body = (f"Document {number} {uuid.uuid4()}.\n\n" + (LINE * 4 + "\n\n") * 500).encode()
        response = client.post(
            f"{path}/documents",
            params={"filename": f"load-{number}.txt"},
            content=body,
            headers={**headers, "Content-Type": "text/plain"},
        )
        if response.status_code == 201:
            sent.append((index, response.json()["id"]))
    time.sleep(4)  # about 30 uploads a minute: under the upload rate limit, over one slot's pace

states: dict[str, int] = {}
for index, document in sent:
    client, headers, path = tenants[index]
    state = client.get(f"{path}/documents/{document}", headers=headers).json().get("status", "?")
    states[state] = states.get(state, 0) + 1
sys.stdout.write(
    "LOAD "
    + json.dumps(
        {
            "seconds": round(time.monotonic() - started, 1),
            "uploaded": len(sent),
            "states_at_stop": states,
        }
    )
    + "\n"
)
