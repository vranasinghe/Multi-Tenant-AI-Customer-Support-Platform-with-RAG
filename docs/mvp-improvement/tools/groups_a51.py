"""Count a JUnit file by preservation group. Usage: python .../groups_a51.py <junit.xml>"""

import json
import runpy
import sys
from pathlib import Path
from xml.etree import ElementTree  # parses only our own pytest output

earlier = Path(__file__).with_name("groups_a5.py").read_text(encoding="utf-8")
namespace: dict[str, object] = {}
exec(earlier[earlier.index("GROUPS = {") : earlier.index("cases = ")], namespace)  # noqa: S102
GROUPS = dict(namespace["GROUPS"])  # type: ignore[call-overload]
GROUPS["A5.1 original ownership"] = ("test_original_ownership",)
GROUPS["A5.1 real-worker crawl"] = ("test_crawl_worker",)

cases = ElementTree.parse(sys.argv[1]).findall(".//testcase")  # noqa: S314


def tally(selected: list[ElementTree.Element]) -> dict[str, int]:
    failed = sum(c.find("failure") is not None or c.find("error") is not None for c in selected)
    skipped = sum(c.find("skipped") is not None for c in selected)
    return {"passed": len(selected) - failed - skipped, "failed": failed, "skipped": skipped}


result: dict[str, object] = {"total": tally(cases)}
for name, needles in GROUPS.items():
    result[name] = tally(
        [c for c in cases if any(n in (c.get("classname") or "") + "." for n in needles)]
    )
print(json.dumps(result, indent=1))
