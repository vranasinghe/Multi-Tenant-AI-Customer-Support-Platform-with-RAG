"""Count a JUnit file by preservation group. Usage: python .../groups_a5.py <junit.xml>"""

import json
import sys
from xml.etree import ElementTree  # parses only our own pytest output

GROUPS = {
    "AUD-01 pool/capacity/lifecycle": ("test_chat_capacity", "test_chat_lifecycle", "test_pool"),
    "AUD-02 citations": ("test_rendered_evidence", "test_citation_provenance"),
    "AUD-03 provider transport": ("test_provider_transport",),
    "AUD-04 proxy trust (unit)": ("test_proxy_trust",),
    "AUD-04 runtime proxy (host-driven)": ("test_runtime_proxy_trust",),
    "A4.1 admission and migration": ("test_chat_admission", "test_chat_migration"),
    "Original audit regressions": (".audit.", ),
    "Auth, route permissions, tenant isolation": (
        "test_auth", "test_route_permissions", "test_tenant_isolation", "tenancy",
    ),
    "Widget": ("test_widget",),
    "Phase 7 analytics": ("test_conversation_analytics", "test_analytics_metrics"),
    "Conversations": ("test_conversations",),
    "Extraction, files, crawler, fetcher": (
        "test_extract", "test_files", "test_html_and_crawler", "test_safe_fetch",
    ),
    "Existing ingestion, deletion, reindex, websites": ("test_knowledge",),
    "Live full-stack ingestion": ("test_live_ingestion",),
    "AUD-05 parser runner": ("test_parser_runner",),
    "AUD-05 tasks and limits": ("test_ingestion_tasks",),
    "AUD-05 lifecycle, fencing, admission": ("test_ingestion_isolation",),
    "AUD-05 real worker": ("test_ingestion_worker",),
}

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
