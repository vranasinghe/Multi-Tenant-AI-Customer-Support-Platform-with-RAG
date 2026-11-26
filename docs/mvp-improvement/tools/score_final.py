"""Recompute the original 60-item audit rubric with the same weights and credit rule.

PASS earns the item's weight, PARTIALLY_IMPLEMENTED half of it, everything else nothing. Only the
items listed below changed; every other item keeps its original status.
"""

import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[3]
original = json.loads((root / "docs/audit/implementation_matrix.json").read_text(encoding="utf-8"))
CHANGES = {
    "P1-03": ("PASS", "HTTPS required for both providers; 159 transport tests; mutation caught"),
    "P1-10": ("PARTIALLY_IMPLEMENTED", "Backup and restore rehearsed locally; alerts and deployment drills not run"),
    "P3-10": ("PASS", "Inbox reads real data with pagination; browser and API tests"),
    "P5-08": ("PARTIALLY_IMPLEMENTED", "Only rendered, authorized sources can be cited; semantic correctness unverified"),
    "P5-10": ("PASS", "Capacity gate 10/10 declared runs and in the full suite; hardware sensitive"),
    "P6-03": ("PASS", "Streaming and source display with provenance enforced"),
}
CREDIT = {"PASS": 1.0, "PARTIALLY_IMPLEMENTED": 0.5}
rows, phases = [], Counter()
for item in original:
    status, evidence = CHANGES.get(item["id"], (item["status"], None))
    score = item["weight"] * CREDIT.get(status, 0.0)
    phases[item["phase"]] += score
    rows.append({
        "id": item["id"], "requirement": item["requirement"], "weight": item["weight"],
        "original_status": item["status"], "original_score": item["score"],
        "status": status, "score": score, "changed": item["id"] in CHANGES,
        "current_evidence": evidence,
    })
result = {
    "original_total": sum(i["score"] for i in original),
    "current_total": sum(r["score"] for r in rows),
    "phases": {str(k): v for k, v in sorted(phases.items())},
    "status_counts": dict(Counter(r["status"] for r in rows)),
    "rows": rows,
}
out = root / "docs/mvp-improvement/evidence/MILESTONE-A-FINAL/score"
out.mkdir(parents=True, exist_ok=True)
(out / "implementation_matrix_current.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print({k: v for k, v in result.items() if k != "rows"})
for r in rows:
    if r["changed"]:
        print(r["id"], r["original_status"], r["original_score"], "->", r["status"], r["score"])
