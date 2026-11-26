"""Preservation and secret check against the snapshot taken before this task.

    python docs/mvp-improvement/tools/verify_final.py <snapshot inventory.sha256>
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/MILESTONE-A-FINAL"
before = {}
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    digest, _, name = line.partition("  ")
    before[name] = digest


def digest(name: str) -> str:
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


listed = subprocess.run(
    ["git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard"],
    cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
).stdout.splitlines()
present = {n for n in listed if (root / n).is_file()}
removed = sorted(n for n in before if n in present or True if not (root / n).is_file())
changed = sorted(n for n, h in before.items() if (root / n).is_file() and digest(n) != h)
added = sorted(n for n in present - set(before) if not n.startswith(out.relative_to(root).as_posix()))

protected = [
    n for n in [*changed, *removed]
    if n.startswith(("docs/audit/", "docs/mvp-improvement/evidence/", "services/api/migrations/versions/"))
    or re.search(r"docs/mvp-improvement/(AUD-0|A4_1_|A5_1_|A6_1_)", n)
]

secrets = []
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    key, sep, value = line.partition("=")
    value = value.strip().strip("'\"")
    if sep and re.search(r"KEY|PASSWORD|SECRET|TOKEN", key) and len(value) >= 16:
        if not value.startswith("change-me"):
            secrets.append(value.encode())
patterns = [
    rb"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9_.-]{24,}",
    rb"__Host-session=(?!\[REDACTED\])[A-Za-z0-9_.-]{20,}",
    rb"\b(sk-(?:proj-)?[A-Za-z0-9]{24,}|AIza[0-9A-Za-z_-]{30,})",
    rb"ci-(?:owner|app|storage)-[0-9a-f]{24,}",
    rb"restore-[0-9a-f]{32}",
]
files = [p for p in out.rglob("*") if p.is_file() and p.name != "artifact-validation.json"]
findings = []
for path in [*files, *(root / n for n in [*changed, *added])]:
    data = path.read_bytes()
    if any(s in data for s in secrets) or any(re.search(p, data) for p in patterns):
        findings.append(path.relative_to(root).as_posix())

report = {
    "inventoried_before": len(before),
    "changed": changed,
    "added_outside_new_evidence": added,
    "removed": removed,
    "protected_files_changed": protected,
    "new_evidence_files": len(files),
    "developer_env_secret_values_checked": len(secrets),
    "secret_findings": findings,
    "scope": "files changed or added by this task and its evidence; not a history audit",
}
(out / "artifact-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: (len(v) if k in ("changed", "added_outside_new_evidence") else v)
                  for k, v in report.items()}, indent=1))
