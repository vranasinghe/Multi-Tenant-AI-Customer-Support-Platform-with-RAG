"""Verify bounded A2 artifacts/preservation; never modifies original audit/A1 evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree

root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/AUD-02"


def read(name: str) -> object:
    return json.loads((out / name).read_text(encoding="utf-8"))


def counts(name: str) -> dict[str, object]:
    tree = ElementTree.parse(out / name)
    suites = tree.getroot().findall("testsuite")
    totals = {key: sum(int(s.get(key, "0")) for s in suites) for key in ["tests", "failures", "errors", "skipped"]}
    failed = [t.get("classname", "") + "::" + t.get("name", "") for t in tree.findall(".//testcase") if t.find("failure") is not None or t.find("error") is not None]
    a1 = [t for t in tree.findall(".//testcase") if any(n in t.get("classname", "") for n in ["test_chat_capacity", "test_chat_lifecycle"])]
    return {**totals, "passed": totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"], "failed_cases": failed, "AUD01_tests": len(a1), "AUD01_failures": sum(t.find("failure") is not None or t.find("error") is not None for t in a1)}


before = read("before_hashes.json")
changed = [name for name, digest in before.items() if not (root / name).is_file() or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest]
expected = ["services/api/app/rag/retrieval.py", "services/api/app/services/chat_prompt.py", "services/api/app/services/conversations.py"]
assert sorted(changed) == sorted(expected), changed
protected = {name: digest for name, digest in before.items() if name not in expected}
assert len(protected) == 331

baseline, focused, existing, backend = [counts(n) for n in ["baseline.xml", "focused-final.xml", "existing-and-a1.xml", "backend-full.xml"]]
assert baseline["failures"] == 1 and baseline["tests"] == 1
assert focused["passed"] == 33 and focused["failures"] == focused["errors"] == focused["skipped"] == 0
assert existing["passed"] == 287 and existing["failures"] == existing["errors"] == existing["skipped"] == 0
assert backend["passed"] == 635 and backend["failures"] == 1 and backend["errors"] == backend["skipped"] == 0
assert backend["failed_cases"] == ["tests.unit.audit.test_prompt_evidence::test_production_embedding_transport_must_require_https"]
assert backend["AUD01_tests"] == existing["AUD01_tests"] == 18
assert backend["AUD01_failures"] == existing["AUD01_failures"] == 0
browser_text = (out / "browser.log").read_text(encoding="utf-8")
browser = json.JSONDecoder().raw_decode(browser_text[browser_text.index("{"):])[0]
assert browser["stats"]["expected"] == 5 and browser["stats"]["unexpected"] == browser["stats"]["flaky"] == browser["stats"]["skipped"] == 0
for name in ["focused-final.json", "existing-and-a1.json", "static-verified.json", "browser.json", "build-rls.json", "rollback-image.json"]:
    assert read(name)["exit_code"] == 0, name
assert read("backend-full.json")["exit_code"] == read("baseline.json")["exit_code"] == 1
rollback = json.loads((out / "rollback-image.log").read_text().splitlines()[1])
assert all(before["services/api/" + name] == digest for name, digest in rollback.items())

patterns = {
    "unredacted_bearer": r"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "unredacted_session_cookie": r"__Host-session=(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "credential_url": r"postgres(?:ql)?(?:\+psycopg)?://[^\s:/]+:(?!\[REDACTED\])[^@\s]+@",
    "provider_key": r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
}
findings = []
files = sorted(p for p in out.rglob("*") if p.is_file() and p.name not in {"artifact-validation.json", "results.json"})
for path in files:
    data = path.read_text(encoding="utf-8", errors="replace")
    findings.extend({"path": str(path.relative_to(root)).replace("\\", "/"), "pattern": key} for key, pattern in patterns.items() if re.search(pattern, data))
assert not findings, findings
results = {
    "decision": "PASS", "scope": "AUD-02 only; local deterministic provenance",
    "baseline": baseline, "focused_including_original_AUD02": focused,
    "new_tests": {"unit": 22, "integration": 10, "passed": 32},
    "existing_and_AUD01": existing, "backend": backend, "browser": browser["stats"],
    "semantic_citation_accuracy": {"status": "BLOCKED", "value": None},
    "original_audit_changed": [], "AUD01_artifacts_changed": [], "changed_existing_application_files": changed,
    "protected_existing_files_unchanged": len(protected), "AUD01_rollback_hashes_match": True,
    "performance": [{k: v for k, v in read("full/" + n).items() if k not in {"raw", "pool"}} for n in ["capacity-1.json", "capacity-10.json", "capacity-50.json", "capacity-100.json"]],
    "note": "Reruns are not additional distinct tests. Original AUD-03 failure is untouched. No deployment/paid model/push.",
}
(out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
validation = {
    "decision": "PASS", "inventory_before": len(before), "protected_unchanged": len(protected),
    "sanitization": {"scope": "high-confidence token/credential patterns in A2 artifacts only; not a secrets-history audit", "findings": findings},
    "artifact_hashes": {str(p.relative_to(out)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    "modified_file_hashes": {name: {"before": before[name], "after": hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in changed},
}
(out / "artifact-validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
print(json.dumps({"decision": results["decision"], "backend": backend, "browser_passes": browser["stats"]["expected"], "protected_unchanged": len(protected), "sanitization_findings": len(findings)}))
