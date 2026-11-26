"""A6.1 diagnostic pytest plugin: the ordered statements and commits of one successful send.

Use with ``-p statement_trace_a61`` on ``test_strict_capacity[1]``. Records statement shapes only,
never parameters. Writes ``AUDIT_OUTPUT_DIR/statements.txt`` for the last send of the test.
"""

import os
import re
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine

trace: list[str] = []
active = {"on": False}


def pytest_configure(config) -> None:
    @event.listens_for(Engine, "before_cursor_execute")
    def before(conn, cursor, statement, parameters, context, executemany):
        if active["on"]:
            trace.append(re.sub(r"\s+", " ", statement).strip()[:150])

    for name in ("commit", "rollback", "begin"):
        event.listen(
            Engine, name, lambda conn, name=name: active["on"] and trace.append(f"-- {name}")
        )


def pytest_runtest_setup(item) -> None:
    module = item.module
    if not hasattr(module, "request") or getattr(module.request, "_traced", False):
        return
    original = module.request

    async def request(app, actor, path, **kwargs):
        send = path.endswith("/messages") and kwargs.get("method", "POST") == "POST"
        if not send:
            return await original(app, actor, path, **kwargs)
        trace.clear()
        active["on"] = True
        try:
            return await original(app, actor, path, **kwargs)
        finally:
            active["on"] = False

    request._traced = True
    module.request = request


def pytest_runtest_teardown(item) -> None:
    if trace:
        folder = Path(os.environ["AUDIT_OUTPUT_DIR"])
        folder.mkdir(parents=True, exist_ok=True)
        numbered, count = [], 0
        for line in trace:
            if not line.startswith("--"):
                count += 1
                line = f"{count:2d} {line}"
            numbered.append(line)
        (folder / "statements.txt").write_text("\n".join(numbered) + "\n")
