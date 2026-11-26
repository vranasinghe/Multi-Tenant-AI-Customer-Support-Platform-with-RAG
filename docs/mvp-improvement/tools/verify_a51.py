"""A5.1 preservation and secret check. Writes only new A5.1 evidence.

Usage (repository root):  python docs/mvp-improvement/tools/verify_a51.py
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[3]
EVIDENCE = [root / "docs/mvp-improvement/evidence" / n for n in ("A5.1", "AUD05-STORAGE", "AUD05-CRAWL")]
before = json.loads((EVIDENCE[0] / "preflight/before_hashes.json").read_text())


def digest(name: str) -> str:
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


listed = subprocess.run(
    ["git", "-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others",
     "--exclude-standard"],
    cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
).stdout.split("\0")
prefixes = tuple(p.relative_to(root).as_posix() + "/" for p in EVIDENCE)
present = {n for n in listed if n and (root / n).is_file() and not n.startswith(prefixes)}
changed = sorted(n for n, h in before.items() if not (root / n).is_file() or digest(n) != h)
removed = sorted(n for n in before if not (root / n).is_file())
added = sorted(present - set(before))

# Audits, earlier evidence and reports, and published migrations must be byte-identical.
protected = [
    n for n in changed
    if n.startswith(("docs/audit/", "docs/mvp-improvement/evidence/", "services/api/migrations/"))
    or re.search(r"docs/mvp-improvement/(AUD-0[1-5]|A4_1)_", n)
]

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
    rb"qa-(?:owner|app|storage-secret)-[0-9a-f]{24}",
]
files = [
    p for folder in EVIDENCE for p in folder.rglob("*")
    if p.is_file() and p.name != "artifact-validation.json"
]
findings = []
for path in [*files, *(root / n for n in [*changed, *added] if (root / n).is_file())]:
    data = path.read_bytes()
    if any(s in data for s in secrets) or any(re.search(p, data) for p in patterns):
        findings.append(path.relative_to(root).as_posix())

report = {
    "inventoried_before": len(before),
    "unchanged": len(before) - len(changed),
    "changed": changed,
    "added": added,
    "removed": removed,
    "protected_files_changed": protected,
    "evidence_file_count": len(files),
    "developer_env_secret_values_checked": len(secrets),
    "secret_findings": findings,
    "secret_scope": "A5.1 changed, added and evidence files; not a history audit",
}
(EVIDENCE[0] / "artifact-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "secret_scope"}, indent=1))
