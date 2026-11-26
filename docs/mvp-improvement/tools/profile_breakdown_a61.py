"""A6.1: where the event-loop thread's CPU went, from a probe cProfile dump.

Usage:  python profile_breakdown_a61.py <profile.pstats>

Groups self time by the package that owns each function, and reports the cumulative time of the
application entry points on the send path (these overlap; they are not additive).
"""

import json
import pstats
import re
import sys
from collections import defaultdict

stats = pstats.Stats(sys.argv[1]).stats  # type: ignore[attr-defined]


def owner(path: str, name: str) -> str:
    if path == "~":
        for needle in ("psycopg", "asyncio", "ssl", "json", "hashlib", "re."):
            if needle in name:
                return f"builtin:{needle.strip('.')}"
        return "builtin:other"
    match = re.search(r"site-packages/([^/]+)", path)
    if match:
        return match[1]
    if "/app/app/" in path:
        return "app"
    if "/app/tests/" in path:
        return "test harness"
    return "stdlib:" + path.rsplit("/", 1)[-1].split(".")[0]


self_time: dict[str, float] = defaultdict(float)
for (path, _line, name), (_cc, _nc, tottime, _ct, _callers) in stats.items():
    self_time[owner(path, name)] += tottime
total = sum(self_time.values())

wanted = {
    "get_auth", "get_tenant_context", "find_active_session", "set_org_context",
    "set_user_context", "validate", "_prepare", "admit", "acquire", "reserve", "search",
    "authorize_chunks", "bot_for", "stream", "check", "event", "jsonable_encoder",
    "solve_dependencies", "request", "assemble", "token_bound", "citations_for",
}
entry = {}
for (path, line, name), (_cc, calls, tottime, cumulative, _callers) in stats.items():
    if name in wanted and ("/app/app/" in path or "fastapi" in path or "/app/tests/" in path):
        key = f"{path.rsplit('/', 2)[-2]}/{path.rsplit('/', 1)[-1]}:{name}"
        entry[key] = {"calls": calls, "cumulative_s": round(cumulative, 3)}

print(
    json.dumps(
        {
            "profiled_self_seconds": round(total, 3),
            "by_package": {
                k: round(v, 3)
                for k, v in sorted(self_time.items(), key=lambda kv: -kv[1])[:18]
            },
            "entry_points": dict(sorted(entry.items(), key=lambda kv: -kv[1]["cumulative_s"])),
        },
        indent=1,
    )
)
