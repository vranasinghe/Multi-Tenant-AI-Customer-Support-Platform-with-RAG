"""Bounded A4 preservation, result and secret check. Writes only new A4 evidence."""

import hashlib
import json
import re
from pathlib import Path
from xml.etree import ElementTree  # parses only our own pytest output

root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/AUD-04"
before = json.loads((out / "before_hashes.json").read_text(encoding="utf-8"))


def digest(name):
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


changed = sorted(n for n, h in before.items() if not (root / n).is_file() or digest(n) != h)
expected = sorted(
    [
        ".env.example",
        ".env.production.example",
        "deploy/deploy.sh",
        "docker-compose.prod.yml",
        "docker-compose.yml",
        "docs/DEPLOY_CONTABO.md",
        "docs/DEVELOPMENT.md",
        "docs/PHASE2_SECURITY_REVIEW.md",
        "docs/WIDGET_DEPLOYMENT.md",
        "docs/mvp-improvement/02_PROGRESS_TRACKER.md",
        "package.json",
        "services/api/Dockerfile",
        "services/api/app/core/config.py",
        "services/api/app/main.py",
    ]
)
assert changed == expected, sorted(set(changed) ^ set(expected))
protected = ("docs/audit/", "docs/mvp-improvement/evidence/", "docs/mvp-improvement/AUD-0")
assert not [n for n in changed if n.startswith(protected)]


def results(name):
    cases = ElementTree.parse(out / name).findall(".//testcase")
    failed = [
        c.get("name")
        for c in cases
        if c.find("failure") is not None or c.find("error") is not None
    ]
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {
        "tests": len(cases),
        "passed": len(cases) - len(failed) - skipped,
        "failed": failed,
        "skipped": skipped,
    }


known = ["test_strict_capacity[100]", "test_chat_migration_roundtrip"]
baseline = results("baseline-backend-full.xml")
final = results("backend-full.xml")
runtime = results("final-runtime-http.xml")
preservation = results("preservation.xml")
assert (baseline["passed"], sorted(baseline["failed"])) == (808, sorted(known))
assert (final["passed"], final["skipped"], sorted(final["failed"])) == (1005, 17, sorted(known))
assert (runtime["passed"], runtime["tests"]) == (17, 17)
assert (preservation["passed"], preservation["failed"]) == (741, known[:1])

# Real values from the developer's .env must not appear in anything A4 wrote.
secrets = []
env = root / ".env"
if env.is_file():
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        value = value.strip().strip("'\"")
        placeholder = value.startswith("change-me")  # published in .env.example
        if sep and re.search(r"KEY|PASSWORD|SECRET|TOKEN", key) and len(value) >= 16 and not placeholder:
            secrets.append(value)
patterns = {
    "unredacted_bearer": r"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "unredacted_session": r"__Host-session=(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    "provider_key": r"\b(sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,})",
}
new_files = [
    "docs/mvp-improvement/AUD-04_IMPLEMENTATION_REPORT.md",
    "docs/mvp-improvement/tools/capture_a4.py",
    "docs/mvp-improvement/tools/verify_a4.py",
    "services/api/app/core/proxy_trust.py",
    "services/api/app/server.py",
    "services/api/tests/integration/test_runtime_proxy_trust.py",
    "services/api/tests/unit/mvp_improvement/test_proxy_trust.py",
]
evidence = sorted(
    p for p in out.rglob("*") if p.is_file() and p.name != "artifact-validation.json"
)
findings = []
for path in [*evidence, *(root / n for n in [*new_files, *changed])]:
    text = path.read_text(encoding="utf-8", errors="replace")
    relative = path.relative_to(root).as_posix()
    findings += [{"file": relative, "pattern": n} for n, p in patterns.items() if re.search(p, text)]
    if any(secret in text for secret in secrets):
        findings.append({"file": relative, "pattern": "value from .env"})

validation = {
    "preservation": "PASS",
    "inventoried_before": len(before),
    "unchanged": len(before) - len(changed),
    "changed_existing_files": {n: {"before": before[n], "after": digest(n)} for n in changed},
    "new_files": {n: digest(n) for n in new_files},
    "evidence_files": {p.relative_to(out).as_posix(): digest(p.relative_to(root)) for p in evidence},
    "baseline": baseline,
    "final": final,
    "runtime": runtime,
    "preservation_run": preservation,
    "secret_scan": {
        "env_values_checked": len(secrets),
        "findings": findings,
        "scope": "A4 files and evidence only; not a repository-history audit",
    },
}
(out / "artifact-validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "unchanged": validation["unchanged"],
            "changed": len(changed),
            "env_values_checked": len(secrets),
            "secret_findings": findings,
        }
    )
)
