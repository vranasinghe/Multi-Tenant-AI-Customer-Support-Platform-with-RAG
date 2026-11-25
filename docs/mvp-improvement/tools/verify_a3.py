"""Bounded A3 preservation/result verification. Writes only new A3 evidence."""

import hashlib
import json
import re
from pathlib import Path
from defusedxml import ElementTree

root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/AUD-03"


def load(name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def tests(name):
    tree = ElementTree.parse(out / name)
    suites = tree.getroot().findall("testsuite")
    totals = {
        key: sum(int(s.get(key, "0")) for s in suites)
        for key in ["tests", "failures", "errors", "skipped"]
    }
    cases = tree.findall(".//testcase")

    def group(needle):
        matched = [c for c in cases if any(n in c.get("classname", "") for n in needle)]
        return {
            "tests": len(matched),
            "failures": sum(
                c.find("failure") is not None or c.find("error") is not None
                for c in matched
            ),
        }

    return {
        **totals,
        "passed": totals["tests"]
        - totals["failures"]
        - totals["errors"]
        - totals["skipped"],
        "AUD01": group(["test_chat_capacity", "test_chat_lifecycle"]),
        "AUD02": group(["test_rendered_evidence", "test_citation_provenance"]),
        "AUD03_new": group(["test_provider_transport"]),
        "original_AUD02": [
            c.get("name")
            for c in cases
            if c.get("name")
            == "test_citations_must_only_reference_sources_actually_rendered"
            and c.find("failure") is None
        ],
        "original_AUD03": [
            c.get("name")
            for c in cases
            if c.get("name") == "test_production_embedding_transport_must_require_https"
            and c.find("failure") is None
        ],
    }


before = load("before_hashes.json")
changed = [
    n
    for n, h in before.items()
    if not (root / n).is_file()
    or hashlib.sha256((root / n).read_bytes()).hexdigest() != h
]
expected = [
    "services/api/app/main.py",
    "services/api/app/core/config.py",
    "services/api/app/integrations/llm.py",
    "services/api/app/rag/embeddings.py",
    "services/api/app/services/chat_work.py",
    "services/api/app/workers/celery_app.py",
    "services/api/tests/unit/rag/test_embeddings.py",
    "services/api/tests/integration/api/mvp_improvement/test_chat_lifecycle.py",
    ".env.example",
    "docker-compose.yml",
    "docs/CHAT_ENGINE.md",
    "docs/INGESTION.md",
    "docs/DEVELOPMENT.md",
    "docs/mvp-improvement/02_PROGRESS_TRACKER.md",
]
assert sorted(changed) == sorted(expected), changed
assert len(before) == 399
assert not any(
    n.startswith(("docs/audit/", "docs/mvp-improvement/evidence/")) for n in changed
)
a1_path = "services/api/tests/integration/api/mvp_improvement/test_chat_lifecycle.py"
reconstructed = (
    "\n".join(
        line
        for line in (root / a1_path).read_text().splitlines()
        if line.strip()
        not in {"allow_insecure_local=True,", '"allow_insecure_local": True,'}
    )
    + "\n"
)
assert any(
    hashlib.sha256(reconstructed.replace("\n", ending).encode()).hexdigest()
    == before[a1_path]
    for ending in ["\n", "\r\n"]
)
baseline, previous, failed_run, failed_repeat, final, preservation, strict = [
    tests(n)
    for n in [
        "baseline.xml",
        "backend-full.xml",
        "backend-final.xml",
        "backend-release.xml",
        "backend-confirmation.xml",
        "preservation.xml",
        "strict-rerun.xml",
    ]
]
assert baseline["tests"] == baseline["failures"] == 1
assert previous["passed"] == previous["tests"] == 793
assert (
    failed_run["passed"] == failed_repeat["passed"] == 794
    and failed_run["failures"] == failed_repeat["failures"] == 1
)
assert strict["passed"] == strict["tests"] == 18
assert final["passed"] == final["tests"] == 795
assert final["errors"] == final["failures"] == final["skipped"] == 0
assert preservation["passed"] == preservation["tests"] == 362
assert final["AUD01"] == preservation["AUD01"] == {"tests": 18, "failures": 0}
assert final["AUD02"] == preservation["AUD02"] == {"tests": 32, "failures": 0}
assert final["AUD03_new"] == {"tests": 159, "failures": 0}
assert len(final["original_AUD02"]) == len(final["original_AUD03"]) == 1
for name in [
    "backend-confirmation",
    "strict-rerun",
    "preservation",
    "release-static",
    "build-final",
    "original-after",
    "browser-confirmation",
]:
    assert load(name + ".json")["exit_code"] == 0
browser_log = (out / "browser-confirmation.log").read_text(encoding="utf-8")
browser = json.JSONDecoder().raw_decode(browser_log[browser_log.index("{") :])[0][
    "stats"
]
assert (
    browser["expected"] == 5
    and browser["unexpected"] == browser["flaky"] == browser["skipped"] == 0
)
patterns = {
    "unredacted_bearer": r"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "unredacted_session": r"__Host-session=(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "credential_url": r"postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:(?!\[REDACTED\])[^@\s]+@",
    "provider_key": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
}
files = sorted(
    p
    for p in out.rglob("*")
    if p.is_file() and p.name not in {"results.json", "artifact-validation.json"}
)
findings = [
    {"file": p.relative_to(out).as_posix(), "pattern": n}
    for p in files
    for n, pattern in patterns.items()
    if re.search(pattern, p.read_text(encoding="utf-8", errors="replace"))
]
assert not findings, findings
results = {
    "decision": "PASS",
    "scope": "AUD-03 local provider transport only",
    "baseline": baseline,
    "backend_previous": previous,
    "backend_capacity_failure": failed_run,
    "backend_capacity_repeat_failure": failed_repeat,
    "strict_rerun": strict,
    "backend_final": final,
    "preservation": preservation,
    "browser": browser,
    "browser_initial_routing_failure_exit": load("browser.json")["exit_code"],
    "browser_cookie_harness_failure_exit": load("browser-ipv4.json")["exit_code"],
    "changed_existing_files": changed,
    "protected_existing_files_unchanged": len(before) - len(changed),
    "original_audit_changed": [],
    "AUD01_AUD02_evidence_changed": [],
    "A1_fixture_only_reverse_hash_matches": True,
    "live_paid_provider": {
        "status": "NOT_RUN",
        "reason": "Not configured or authorized; local synthetic transport validation only",
    },
    "semantic_AI_quality": {"status": "BLOCKED", "value": None},
}
(out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
new_code = [
    "services/api/app/core/provider_urls.py",
    "services/api/tests/unit/mvp_improvement/test_provider_transport.py",
    "services/api/tests/support/provider_server.py",
    "docs/mvp-improvement/AUD-03_IMPLEMENTATION_REPORT.md",
    "docs/mvp-improvement/tools/capture_a3.py",
    "docs/mvp-improvement/tools/verify_a3.py",
    "docs/mvp-improvement/tools/generate_a3_tls.py",
    "docs/mvp-improvement/tools/playwright_a3.config.ts",
    "docs/mvp-improvement/tools/check_a3_resolution.py",
]
new_code += [
    p.relative_to(root).as_posix()
    for p in (root / "services/api/tests/support/provider_tls").glob("*")
    if p.is_file()
]
validation = {
    "decision": "PASS",
    "before_count": len(before),
    "protected_unchanged": len(before) - len(changed),
    "sanitization": {
        "findings": findings,
        "scope": "high-confidence token patterns in A3 artifacts; not a history secrets audit; TLS leaf key is public synthetic test-only material",
    },
    "modified_file_hashes": {
        n: {
            "before": before[n],
            "after": hashlib.sha256((root / n).read_bytes()).hexdigest(),
        }
        for n in changed
    },
    "new_file_hashes": {
        n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in new_code
    },
    "artifact_hashes": {
        p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    },
}
(out / "artifact-validation.json").write_text(
    json.dumps(validation, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        {
            "decision": "PASS",
            "backend": final["passed"],
            "AUD01": final["AUD01"],
            "AUD02": final["AUD02"],
            "AUD03_new": final["AUD03_new"],
            "protected_unchanged": len(before) - len(changed),
            "sanitization_findings": len(findings),
        }
    )
)
