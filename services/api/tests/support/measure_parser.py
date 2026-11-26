"""The real parser child, reporting its own peak memory and CPU in the result's title.

Used to check that the default parser budgets fit supported documents
(``docs/mvp-improvement/tools/measure_a5.py``). Limits are exactly the production child's.
"""

from __future__ import annotations

import json
import resource
from pathlib import Path
from typing import Any

from app.rag import parser_process


def _measured(request: dict[str, Any], data: bytes) -> dict[str, Any]:
    result = parser_process.parse(request, data)
    status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result["title"] = json.dumps(
        {
            "peak_address_space_mib": round(int(status["VmPeak"].split()[0]) / 1024),
            "peak_resident_mib": round(int(status["VmHWM"].split()[0]) / 1024),
            "cpu_seconds": round(usage.ru_utime + usage.ru_stime, 2),
        }
    )
    return result


if __name__ == "__main__":
    parser_process.serve(_measured)
