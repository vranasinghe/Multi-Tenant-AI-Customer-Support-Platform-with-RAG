"""Bounded A4.1 preservation, result and secret check. Writes only new A4.1 evidence."""

import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree  # parses only our own pytest output

root = Path(__file__).resolve().parents[3]
evidence = root / "docs/mvp-improvement/evidence"
before = json.loads((evidence / "PERF-01/preflight/before_hashes.json").read_text())


def digest(name):
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


changed = sorted(n for n, h in before.items() if not (root / n).is_file() or digest(n) != h)
expected = sorted(
    [
        "docs/CHAT_ENGINE.md",
        "docs/mvp-improvement/02_PROGRESS_TRACKER.md",
        "services/api/app/services/chat_controls.py",
        "services/api/app/services/conversations.py",
        "services/api/migrations/versions/20261125_0007_conversation_analytics.py",
        "services/api/tests/integration/test_chat_migration.py",
        "services/api/tests/support/database.py",
    ]
)
assert changed == expected, sorted(set(changed) ^ set(expected))


def results(name):
    cases = ElementTree.parse(evidence / name).findall(".//testcase")
    failed = sum(c.find("failure") is not None or c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {"passed": len(cases) - failed - skipped, "failed": failed, "skipped": skipped}


final = results("PERF-01/final-full-suite.xml")
runtime = results("LINT-01/runtime-proxy.xml")
assert final == {"passed": 1016, "failed": 0, "skipped": 17}, final
assert runtime == {"passed": 17, "failed": 0, "skipped": 0}, runtime
series = {}
for name in ("idle-baseline-5", "devstack-baseline-5", "idle-after-fix-5", "devstack-after-fix-5"):
    summary = json.loads((evidence / "PERF-01/series" / name / "summary.json").read_text())
    assert summary["completed_runs"] == summary["planned_runs"] == 5
    series[name] = {
        "failed_runs": summary["failed_runs"],
        "c100": summary["successful_p95_ms_c100"],
    }
assert series["idle-after-fix-5"]["failed_runs"] == 0
assert series["devstack-after-fix-5"]["failed_runs"] == 0

secrets = []
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    key, sep, value = line.partition("=")
    value = value.strip().strip("'\"")
    if sep and re.search(r"KEY|PASSWORD|SECRET|TOKEN", key) and len(value) >= 16:
        if not value.startswith("change-me"):
            secrets.append(value.encode())
patterns = [
    rb"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    rb"__Host-session=(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    rb"\b(sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,})",
]
new_files = [
    "docs/mvp-improvement/A4_1_STABILIZATION_REPORT.md",
    "docs/mvp-improvement/tools/capture_a41.py",
    "docs/mvp-improvement/tools/perf01_series.py",
    "docs/mvp-improvement/tools/perf_probe.py",
    "docs/mvp-improvement/tools/mig_probe.py",
    "docs/mvp-improvement/tools/verify_a41.py",
    "services/api/tests/unit/mvp_improvement/test_chat_admission.py",
]
files = [
    p
    for area in ("PERF-01", "MIG-01", "LINT-01")
    for p in (evidence / area).rglob("*")
    if p.is_file() and p.name != "artifact-validation.json"
]
findings = []
for path in [*files, *(root / n for n in [*new_files, *changed])]:
    data = path.read_bytes()
    if any(s in data for s in secrets) or any(re.search(p, data) for p in patterns):
        findings.append(path.relative_to(root).as_posix())

(evidence / "PERF-01/artifact-validation.json").write_text(
    json.dumps(
        {
            "inventoried_before": len(before),
            "unchanged": len(before) - len(changed),
            "changed_existing_files": {n: {"before": before[n], "after": digest(n)} for n in changed},
            "new_files": {n: digest(n) for n in new_files},
            "evidence_file_count": len(files),
            "final_suite": final,
            "runtime_suite": runtime,
            "series": series,
            "secret_findings": findings,
            "secret_scope": "A4.1 files and evidence only; not a history audit",
        },
        indent=2,
    ),
    encoding="utf-8",
)
print(
    json.dumps(
        {"unchanged": len(before) - len(changed), "changed": len(changed), "files": len(files),
         "env_values_checked": len(secrets), "secret_findings": findings[:10]}
    )
)
