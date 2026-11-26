"""A5.1 preflight: revision, status, SHA-256 inventory, uncommitted patch, containers, env flags.

Records presence of developer environment values, never the values. Run once from the repository
root before any A5.1 source change.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
out = root / "docs/mvp-improvement/evidence/A5.1/preflight"
if (out / "preflight.json").exists():
    sys.exit("preflight already recorded; it is never overwritten")
out.mkdir(parents=True, exist_ok=True)


def run(*args: str) -> str:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


def git(*args: str) -> str:
    return run("git", "-c", "core.quotepath=false", *args)


# Tracked plus untracked-but-not-ignored files: the whole source/configuration surface. The
# A5.1 evidence folder and these tools are this task's own output.
names = sorted(
    n
    for n in git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split("\0")
    if n
    and not n.startswith("docs/mvp-improvement/evidence/A5.1/")
    and not n.endswith("_a51.py")
    and (root / n).is_file()
)
hashes = {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}
(out / "before_hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
(out / "pre_existing_uncommitted.patch").write_text(git("diff", "HEAD"), encoding="utf-8")

flags: dict[str, object] = {}
for line in (root / ".env").read_text(encoding="utf-8").splitlines():
    key, sep, value = line.partition("=")
    if not sep or key.startswith("#"):
        continue
    if key in {"APP_ENV", "LOG_LEVEL", "LLM_PROVIDER", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL"}:
        flags[key] = value.strip()
    elif "KEY" in key:
        flags[f"{key}_present"] = bool(value.strip())

record = {
    "head": git("rev-parse", "HEAD").strip(),
    "branch": git("branch", "--show-current").strip(),
    "status": git("status", "--porcelain=v1").splitlines(),
    "stash": git("stash", "list").splitlines(),
    "files_inventoried": len(hashes),
    "developer_env_flags": flags,
    "containers": run("docker", "ps", "-a", "--format", "{{.Names}} | {{.Status}}").splitlines(),
    "docker_info": run(
        "docker",
        "info",
        "--format",
        "CPUs={{.NCPU}} MemBytes={{.MemTotal}} Cgroup={{.CgroupVersion}} Server={{.ServerVersion}}",
    ).strip(),
}
(out / "preflight.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print(json.dumps({k: record[k] for k in ("head", "files_inventoried", "docker_info")}))
