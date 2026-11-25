"""Validate report artifacts and source preservation without application access."""
import csv
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

root = Path('docs/audit')
evidence = root / 'evidence'
inventory = json.loads((evidence / 'source_inventory_before.json').read_text())
changed = [item['path'] for item in inventory if not Path(item['path']).exists() or hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']]
preservation = {'files_checked': len(inventory), 'changed_files': changed}
(evidence / 'source_preservation.json').write_text(json.dumps(preservation, indent=2))
assert not changed, 'Pre-existing application/configuration files changed'
reports = sorted(root.glob('[0-9][0-9]_*.md'))
assert len(reports) == 12
assert [int(p.name[:2]) for p in reports] == list(range(1, 13))
cases = [json.loads(line) for line in (root / 'rag_evaluation_dataset.jsonl').read_text(encoding='utf-8').splitlines() if line]
results = json.loads((evidence / 'rag_results.json').read_text())
corpus = json.loads((root / 'rag_evaluation_corpus.json').read_text())
copy = json.loads(Path('services/api/tests/integration/api/audit/dataset.json').read_text())
assert copy['cases'] == cases and copy['corpus'] == corpus
assert len(cases) == len(results) == 100
assert len({r['id'] for r in results}) == 100
with (root / 'rag_evaluation_results.csv').open(newline='', encoding='utf-8') as handle:
    rows = list(csv.DictReader(handle))
assert len(rows) == 100 and [r['id'] for r in rows] == [r['id'] for r in results]
assert all(r['status'] == 'BLOCKED' and r['generated_answer'] is None and r['actual_citations'] is None for r in results)
assert sum(r['retrieval_hit_at_5'] is True for r in results) == 68
assert sum(r['retrieval_hit_at_5'] is not None for r in results) == 80
assert sum(r['leaked_chunks'] for r in results) == 0
matrix = json.loads((root / 'implementation_matrix.json').read_text())
assert len(matrix) == 60 and sum(r['score'] for r in matrix) == 80.5
for row in matrix:
    for name in row['file_paths'].split('; '):
        assert Path(re.sub(r':\d+$', '', name)).exists(), name
counts = {}
for path in evidence.glob('*.xml'):
    tests = list(ET.parse(path).getroot().iter('testcase'))
    counts[path.name] = {'tests':len(tests), 'failed':sum(t.find('failure') is not None or t.find('error') is not None for t in tests), 'skipped':sum(t.find('skipped') is not None for t in tests)}
assert counts['baseline.xml'] == {'tests':582, 'failed':0, 'skipped':0}
assert counts['audit-security.xml']['failed'] == 2
assert counts['audit-pool.xml']['failed'] == 1
assert counts['audit-workflow.xml']['failed'] == 0

# Report only artifact names/counts for potential tokens, never their contents.
suspect = []
for path in evidence.iterdir():
    if path.suffix not in {'.log', '.xml'}:
        continue
    data = path.read_text(encoding='utf-8', errors='replace')
    patterns = [r'(?i)__Host-session=[A-Za-z0-9_.-]{20,}', r'Bearer [A-Za-z0-9_.-]{30,}', r'\bsk-[A-Za-z0-9_-]{20,}']
    if any(re.search(pattern, data) for pattern in patterns):
        suspect.append(path.name)
assert not suspect, 'Possible raw tokens in evidence artifacts: ' + ','.join(suspect)
output = {'status':'PASS', 'required_reports':len(reports), 'dataset_cases':len(cases), 'csv_rows':len(rows), 'case_categories':dict(Counter(r['category'] for r in results)), 'junit_files':counts, 'source_preservation':preservation, 'raw_token_patterns_detected':len(suspect), 'scope':'Artifact consistency and bounded token-pattern check; not a comprehensive secrets scanner'}
(evidence / 'artifact_validation.json').write_text(json.dumps(output, indent=2))
print(json.dumps(output, indent=2))
