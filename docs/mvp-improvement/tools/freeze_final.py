"""SHA-256 inventory of everything except documentation and evidence.

    python docs/mvp-improvement/tools/freeze_final.py record|verify <file>
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
names = subprocess.run(
    ["git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard"],
    cwd=root, capture_output=True, text=True, encoding="utf-8", check=True,
).stdout.splitlines()
now = {
    n: hashlib.sha256((root / n).read_bytes()).hexdigest()
    for n in sorted(names)
    if n and (root / n).is_file() and not n.startswith(("docs/", "graphify-out/"))
}
mode, target = sys.argv[1], Path(sys.argv[2])
if mode == "record":
    if target.exists():
        sys.exit("a freeze is never overwritten")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(now, indent=1), encoding="utf-8")
    print(f"frozen {len(now)} files")
else:
    before = json.loads(target.read_text(encoding="utf-8"))
    drift = sorted(n for n in set(before) | set(now) if before.get(n) != now.get(n))
    print(json.dumps({"files": len(now), "changed_since_freeze": drift}))
    sys.exit(1 if drift else 0)
