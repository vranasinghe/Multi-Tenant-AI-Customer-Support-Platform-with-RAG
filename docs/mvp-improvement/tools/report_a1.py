"""Render A1 deliverables from preserved execution artifacts; does not run the application."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

root = Path('docs/mvp-improvement')
e = root / 'evidence/AUD-01'
metric_dir = 'release-validation' if (e/'release-validation').exists() else 'strict-final'
metrics = [json.loads((e / f'{metric_dir}/capacity-{n}.json').read_text()) for n in (1,10,50,100)]
fairness = json.loads((e / metric_dir / 'fairness.json').read_text())
before = json.loads((e / 'baseline-performance.json').read_text())[0]
collector = json.loads((e / 'original-full-performance.json').read_text())
short = json.loads((e / 'original-short-performance.json').read_text())[0]
counts = {}
for name in ('baseline','backend-full','strict-final','original-short','original-full'):
    cases = list(ET.parse(e / (name+'.xml')).getroot().iter('testcase'))
    counts[name] = dict(tests=len(cases),failed=sum(t.find('failure') is not None or t.find('error') is not None for t in cases),skipped=sum(t.find('skipped') is not None for t in cases))
if (e/'backend-final.xml').exists():
    final_cases=list(ET.parse(e/'backend-final.xml').getroot().iter('testcase'))
    counts['backend-full']=dict(tests=len(final_cases),failed=sum(t.find('failure') is not None for t in final_cases),skipped=sum(t.find('skipped') is not None for t in final_cases))
full_path=e/('backend-final.xml' if (e/'backend-final.xml').exists() else 'backend-full.xml')
full_seconds=float(next(ET.parse(full_path).getroot().iter('testsuite')).get('time'))
original = json.loads((e / 'before_hashes.json').read_text())
changed = [p for p,h in original.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
audit_changed = [p for p in changed if p.startswith('docs/audit/')]
assert not audit_changed
protected = ['services/api/app/services/chat_prompt.py','services/api/app/rag/retrieval.py','services/api/app/rag/embeddings.py','services/api/tests/unit/audit/test_prompt_evidence.py','services/api/tests/integration/api/audit/test_implementation_audit.py']
assert all(p not in changed for p in protected)
records = []
for p in sorted(e.glob('*.json')):
    d = json.loads(p.read_text(encoding='utf-8-sig'))
    if isinstance(d, dict) and 'command' in d:
        records.append(d)
assert counts['backend-full'] == dict(tests=604,failed=2,skipped=0)
assert counts['strict-final'] == dict(tests=18,failed=0,skipped=0)
report = dict(decision='PASS',scope='AUD-01 only; local isolated validation',git_status='UNAVAILABLE: no .git directory; git status exited 128',
              backend=counts['backend-full'],new_tests=counts['strict-final'],browser=dict(passed=5,failed=0),
              protected_unchanged=protected,audit_changed=audit_changed,changed_existing_files=changed,
              performance=[{k:v for k,v in m.items() if k!='raw'} for m in metrics],fairness=fairness,
              known_unrelated_failures=['AUD-02: rendered evidence citation boundary','AUD-03: production HTTP embedding configuration'],
              commands=records,overall_mvp_decision='NOT READY (unchanged; later AUD/milestones not executed)')
(e/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')

table = ['| Concurrency / requests | Proven ASGI overlap | Complete / rejected / failed | Success P95 ms | Reject P95 ms | Success/s | Pool peak / checkout / checkin |', '|---|---|---|---|---|---|---|']
for m in metrics:
    p=m['pool']
    table.append(f"| {m['concurrency']} / {m['requests']} | {m['overlap_peak']} | {m['success']} / {m['rejected']} / {m['failed']} | {m['successful_p95_ms']:.2f} | {m['rejected_p95_ms']:.2f} | {m['successful_requests_per_second']:.2f} | {p['peak']} / {p['checkouts']} / {p['checkins']} |")
commands = ['| Captured run | Exit | Wall s | Exact command / record |', '|---|---|---|---|']
for c in records:
    command=c['command'].replace('|','\\|')
    commands.append(f"| {c['id']} | {c['exit_code']} | {c['duration_seconds']} | `{command}`; [log](evidence/AUD-01/{c['log']}) |")
files='\n'.join('- `'+p+'`' for p in changed if not p.startswith('docs/'))
content = f'''
# AUD-01 implementation report — Milestone A1

Date: 22 November 2026 (Asia/Colombo). Final AUD-01 decision: **PASS for the tested local scope**. Overall MVP readiness remains **NOT READY**. This report closes A1 only; AUD-02 through AUD-07 and subsequent milestones have not been implemented.

## 1. Executive summary

The reproduced ten-request burst returned **10 HTTP 500s**, with a 30-second QueuePool wait. After A1, the unchanged original ten-request regression completed **10 HTTP 200s**, and the original four-stage collector returned successful replies plus controlled 429s, with zero 500s. New strict tests verify terminal SSE content, persisted messages/usage, actual simultaneous overlap, pool reconciliation, second-tenant work, public widget lifecycle, authorization changes and bounded embedding cancellation.

The full backend run produced **602 PASS / 2 FAIL / 0 SKIP (604 tests)** in {full_seconds:.2f} seconds. The only failures are the unchanged AUD-02 citation and AUD-03 production HTTP embedding regressions. All **18 new A1 tests passed** in that run and again in the final focused run (16.83 seconds). The final focused run strengthened repeated timeout checking to five timeouts as well as five cancellations. A subsequent final full-suite run also verifies the child's independent hard deadline with no supervising parent timeout; no application changes followed that final run. Five existing browser tests passed; backend Ruff/format/mypy, runtime image build, local smoke and RLS check passed.

No pool size increase, migration, dependency addition, paid provider call, external deployment or Git push occurred. Original audit reports/evidence and their dedicated tests remain unchanged. Git status was attempted and exited 128 because **this workspace has no `.git` directory**; before/after file hashes identify changes instead. No Git branch/commit status is invented.

## 2. Baseline reproduction and safety

Before application edits, `baseline.log` recorded local Compose services and safe settings flags: APP_ENV local, demo LLM, hash embeddings, both real-provider-key presence flags false. The existing API fixture creates/drops a random `chatbot_test_*` database using real migrations and uses isolated Redis DB 15; the named baseline used those fixtures, not customer data. Test actors/documents are fictional. Tests using Redis DB 15 ran serially. Browser tests create separate local accounts; the local live-ingestion test exercises existing Celery/S3 services without paid calls.

The exact baseline command and exit are in the execution table below. It failed one test as expected, in 31.60 seconds; captured wall time including environment inspection was 35.625 seconds. [baseline-performance.json](evidence/AUD-01/baseline-performance.json) records 10/10 HTTP 500, successful rate 0/s, P50 {before['p50_ms']:.2f} ms and P95 {before['p95_ms']:.2f} ms. The log contains `QueuePool limit of size 5 overflow 5 ... timeout 30.00`. [baseline.xml](evidence/AUD-01/baseline.xml) preserves the failure. The original audit's earlier 9/10 confirmation is historical; this execution reproduced 10/10, which reflects scheduling variation rather than a different finding.

Outputs use `docs/mvp-improvement/evidence/AUD-01/` and separate `/tmp/mvp-improvement/...` container paths. The original `docs/audit/` outputs were never used as writable capture destinations.

## 3. Confirmed root causes

1. Request auth/membership reads retained an outer session through the handler/SSE response. Conversation service lookups checked out a second session; ten outer sessions could consume the default 5+5 pool before Redis admission ran.
2. The dashboard route and preparation both looked up the conversation. Idle session touching also opened an independent session while its auth read checkout was retained.
3. Preparation held a DB transaction across synchronous query embedding. Cancelling `asyncio.to_thread` would leave the underlying operation running.
4. Widget authentication opened origin resolution inside an existing DB session; bootstrap called conversation creation while retaining another session.
5. Merely limiting setup did not bound the earlier authentication burst. Measured early attempts reached peak ten checkouts and failed the acceptance latency gate even after eliminating the deadlock.
6. Pool checkout used SQLAlchemy's implicit 30-second wait; driver connect_timeout=5 was not a pool wait limit. Before-stream interruption could also leave a committed reservation nonterminal.

## 4. Technical implementation

- `require_chat` reuses the existing audited `require`/tenant resolver, captures a **frozen scalar ChatAccess** (org/user/session IDs, permission and verified requirement) and rolls back the auth read before service work. Existing CRUD unit-of-work behavior remains. Idle touch releases the auth-only read transaction before its separate timestamp transaction, then restores user context.
- Chat-related auth lookups receive a bounded process-local gate: up to four concurrent lookups by default, scaled down with the pool; two-second wait, then sanitized 503. The slot is released immediately after the detached context is built, before service I/O/streaming. These routes are identified by their conversation/widget-management paths; denial/cancellation closes/releases the gate too.
- Validated tenant rate checks and Redis org/conversation leases run before expensive preparation. A bounded **0.9-second** lease retry window lets short admitted requests drain instead of rejecting nearly every burst. Org cap remains **three**. Concurrent turns of one conversation still serialize through the same atomic Redis lease.
- Chat setup has a separate fail-fast process-local capacity, configurable at eight and scaled to pool size. It wraps DB read → no-DB embedding → DB retrieval/reservation/persistence. It is released before provider generation. Gates do not create hard physical reserved DB slots; actual occupancy and tenant fairness are measured below.
- Only one preparation conversation lookup remains. Every new tenant transaction sets its RLS context. Dashboard session/user/membership/permission/org state, or scoped widget token/key/domain/org state, is rechecked after embedding before committing messages/reservations or calling the provider.
- Local hash queries execute as bounded pure work on <=8k query text, with no thread. Remote query embedding executes the **existing sync adapter in a fresh child interpreter**. The setup gate bounds simultaneous children. Credentials/input travel through stdin, not argv/logs; child environment excludes server secrets/DB clients. Timeout/cancellation kills and reaps the child, including cancellation during process creation. An independent child-side hard wall watchdog also terminates a stalled operation if its API supervisor disappears. No executor queue or abandoned background embedding thread remains. This is query work containment, not AUD-05 document parser isolation or an AUD-03 transport fix.
- Widget origin resolution can use the caller's existing session. Bootstrap creates conversation and capability in one transaction, preserving resume locking/token rotation and counters; no nested service checkout or orphan conversation commit is required.
- Pool checkout timeout is now two seconds; pool size remains five plus overflow five. Recognized pre-stream SQLAlchemy pool exhaustion maps to `503 chat_unavailable`/Retry-After. Setup/auth capacity exhaustion is also controlled 503; org/conversation saturation remains 429. Other exceptions retain existing handling, and SSE errors keep the existing contract.
- Cancellation attempts owner-token-safe Redis release even if the acquisition script may already have executed. Committed-but-not-started turns become interrupted and their usage becomes settled **without refunding conservative charges**. Cancellation during commit attempts the same idempotent cleanup. Stream finalization and pre-stream cleanup remain shielded; hard process loss/Redis or DB unavailability retains bounded TTL/conservative accounting fallback.

## 5. Before/after architecture

```mermaid
flowchart TD
    B[Before: request auth holds DB connection] --> L[Route lookup needs second connection]
    L --> D[Duplicate preparation lookup before admission]
    D --> E[DB held during embedding and SSE lifecycle]
    E --> X[Pool starvation and 30-second 500s]
    N[After: bounded auth lookup] --> S[Frozen validated context and release checkout]
    S --> A[Bounded Redis org/conversation admission]
    A --> R[Short scoped preparation read]
    R --> Q[No DB held: bounded cancellable embedding]
    Q --> V[Fresh authorization and scoped retrieval/reservation transaction]
    V --> G[Release setup resources; stream provider output]
    G --> F[Short scoped finalization and lease release]
```

## 6. Modified source/configuration files

{files}

New application modules: `services/api/app/services/chat_access.py`, `chat_work.py`, `query_process.py`. The existing `identity/sessions.py` touch function remains unchanged; its call order/lifetime was repaired in `api/deps.py`. Added configuration is `DB_POOL_TIMEOUT_SECONDS=2`, `CHAT_SETUP_CAPACITY=8`, `CHAT_ADMISSION_WAIT_SECONDS=0.9`, documented in `.env.example` and wired through Compose. `docs/CHAT_ENGINE.md` has an additive stabilization description. No frontend, widget bundle, dependency lock or migration was changed.

The before snapshot covers 230 existing application/test/audit/config files. `results.json` lists changed paths and protected unchanged files. Original audit/source files outside this approved scope were not rewritten by format tools.

## 7. New and preserved tests

New typed tests are in `services/api/tests/integration/api/mvp_improvement/test_chat_capacity.py` and `test_chat_lifecycle.py` (18 collected cases): four barrier-synchronized capacity stages, saturated-tenant fairness, pool-size-one lifecycle plus a ten-request stale-touch burst, six post-embedding authorization mutations, bounded pool failure, repeated child cancellation/timeout, real local fixture embedding success, setup capacity, pre-stream settled usage and preparation cancellation. Test providers are fictional/local; no semantic quality claim is made.

The original audit short regression and full collector were executed unchanged. A passing collector alone is not acceptance: new tests parse terminal SSE, reject error/truncated streams, assert exact expected content/status, inspect persisted messages/settled 110-token fixture usage, ensure no assistant rows for rejected turns, and verify actual Redis lease cleanup. They require ten successes at concurrency one and at least max(3,N/4) successful requests at higher loads, so a reject-everything implementation fails.

Original auth, RBAC, membership, FORCE RLS, cross-tenant retrieval/IDOR, provider failure, accounting/quota, ASGI 2.3/2.4 disconnect/socket error, public capability and ingestion tests ran in the full suite. New API input never accepts roles/tenant context/history from the client. Original audit tests and 100-case benchmark labels/corpus were not weakened or edited.

## 8. Before/after performance

Fresh before baseline (10 overlapping requests): **0 complete / 0 controlled rejection / 10 HTTP 500**, P95 {before['p95_ms']:.2f} ms. Unchanged original short regression after: **{short['statuses']}**, P95 {short['p95_ms']:.2f} ms. Both use the same default pool and org cap.

The original full collector after returned 1→10 HTTP 200; 10→10 HTTP 200; 50→47 HTTP 200 +3 HTTP 429; 100→48 HTTP 200 +52 HTTP 429. Mixed-response P95s were respectively 37.12, 221.09, 1063.52 and 1669.87 ms. That collector does not validate terminal SSE or enforce its full-stage failure gate, so **the following strict-capacity tests in the final full-suite run are the acceptance evidence**:

''' + '\n'.join(table) + f'''

Totals: {sum(m['success'] for m in metrics)} complete, {sum(m['rejected'] for m in metrics)} controlled rejections, **zero failed requests / unexpected 500 / harness timeout** out of 170. Every stage has real successes; 100-concurrency success is {metrics[-1]['success']}%, not a rejection-only workaround. New limits were not bypassed in application defaults; only the capacity fixture raises minute/monthly quotas so infrastructure results are not masked by quota depletion. Original default-rate/quota regression tests remain passing.

Each stage uses asyncio barriers plus measured in-flight counters: observed overlap equals 1/10/50/100. Provider peaks were all within the configured cap, and SQLAlchemy events observed simultaneous checkout peaks above one. This is actual overlapping ASGI work, not a loop of sequential requests labelled concurrent.

All success P95 values satisfy <=2,000 ms; rejection P95 <=3,000 ms. Empty rejection groups show zero as N/A sentinel, not an observed zero-latency response. Percentiles use floor((N-1)*p), preserving the original convention. TTFT is the first ASGI delta callback, not browser/network/provider TTFT. Local fixture timings include authentication, DB, Redis and deterministic 10 ms generation; they are not production-model capacity or latency guarantees.

## 9. Pool observations and resource reconciliation

Peak default-pool occupancy in the final workload was **{max(m["pool"]["peak"] for m in metrics)} of ten**, not a guaranteed eight. Each stage ended with zero checkouts and equal checkout/checkin counts (table above). The fairness run measured peak {fairness["pool"]["peak"]} and {fairness['pool']['checkouts']} checkouts/{fairness['pool']['checkins']} checkins, ending at zero. A paused provider-only stream held **zero** database connections before tenant B started work. Setup active count returned to zero, provider active count returned to zero and Redis active/conversation lease keys were empty after graceful completion.

The pool-size-one test (one connection, no overflow) covers stale session touch, conversation create/send/list/transcript, member widget issuance, origin config/verification, public bootstrap/resume/auth/history/send and ten truly overlapping stale-touch reads. It completed without nested checkout; final pool occupancy zero. It demonstrates structural single-checkout behavior at reduced capacity rather than hiding deadlock with a larger pool. A forced occupied pool returns a sanitized 503 within the unchanged <=3-second gate.

The setup cap alone does **not** reserve two physical DB connections. Auth gating, short lifetimes and org leases together produced the measured behavior. Unrelated authorized chatbot reads and public bootstrap/transcript/history were included in fairness testing. Other workload mixes, sustained many-tenant load and actual deployment topology remain outside this local proof.

## 10. Tenant fairness

Tenant A sent ten simultaneous requests; three provider streams were deliberately held, reaching the org cap. During that saturation tenant B completed **20/20 unrelated authorized chatbot reads**, **5/5 valid chats**, four transcript reads, four concurrent public bootstraps and one public history call, all HTTP 200. A's pending work later drained with ten successful completions. No reserved provider-only checkout blocked B.

Idle B read P95: **{fairness['idle_p95_ms']:.2f} ms**. Saturated B read P95: **{fairness['busy_read_p95_ms']:.2f} ms**. Both gates passed: busy <=1,000 ms and <=2×idle+100 ms. This is measured fairness under the declared two-tenant fixture, not a universal scheduler isolation guarantee.

## 11. Security and cancellation validation

All six mutations performed **during the embedding boundary** were rejected before LLM dispatch: session revocation, membership removal, role demotion, organization restriction, widget key rotation and domain deletion. Tests assert 401/403/404 as appropriate, provider peak zero, no messages/reservations, no retained checkout/setup permit and empty org active lease. Original forced-RLS/tenant/manipulated-ID tests passed; no cross-tenant leakage was observed in exercised tests.

Five real remote-query cancellations killed/reaped the child, with cleanup around milliseconds and well below the 2-second gate; five repeated 0.25-second timeouts likewise ended with no children/setup permits. The child-side watchdog test also exits with its explicit deadline code 124 without a supervising ChatWork timeout. The local HTTP fixture uses a fictional key and exercises the existing compatible embedding adapter without a paid request. A local successful remote-query fixture verifies a real returned 1536-vector. During blocked embedding, the app had zero pool checkouts. No query thread pool exists, so repeated abandonment cannot accumulate executor threads.

Preparation cancellation before reservation leaves no usage; pre-stream close after commit marks the assistant interrupted and usage settled while preserving its conservative charge. Existing provider failure, quota atomicity, disconnect and usage reconciliation tests pass. If Redis/DB is unavailable during cleanup, owner-token leases/TTL and conservative accounting still form the fail-closed fallback; hard process termination cannot be claimed equivalent to graceful cleanup.

The original log-hygiene tests passed. Added capture tooling redacts credential-bearing DB URLs and bearer/cookie tokens. A final bounded artifact token-pattern check is recorded separately; it is not a repository-history secrets audit.

## 12. Actual failures and iteration history

- Baseline: one reproduced A1 failure, ten pool-timeout 500s; preserved.
- First strict attempt: 12 passed/two failed. At 100 concurrency, 21 successes did not meet the >=25 gate. The key-rotation test fixture used a value rejected by the existing key format constraint; corrected to a valid fictional key, without weakening the guard.
- Second strict attempt: 13 passed/one failed; success P95 2297.74 ms exceeded 2,000. Third: 13 passed/one failed, P95 2154.79 ms. The implementation was improved with bounded auth admission; limits were then tuned to a 0.9-second lease wait to fit the unchanged latency gate. No acceptance threshold was relaxed.
- A temporary Ruff ASYNC110 warning in the test's polling loop was resolved using an Event. Final lint/format/mypy all pass. Earlier lint output remains in captured logs where recorded.
- Fourth strict run: 17 passed. Full suite: 602 passed/two unrelated failed. Final strict run: 18 passed (adds the successful remote-query contract and repeats timeout assertions). Final full-suite revalidation after the independent child watchdog: 602 passed/two unrelated failed. See JUnit/logs for precise run snapshots rather than summing reruns as independent coverage.
- **AUD-02 and AUD-03 remain FAIL.** The full suite exits **1**, not green. Their implementations, failing tests and original evidence remain intact. AUD-04 through AUD-07 were not implemented.

## 13. Commands and evidence

All commands below were actually executed at the repository root. Durations are captured subprocess wall times; pytest test durations differ. Metadata and full redacted logs are under `evidence/AUD-01/`. Backend test fixtures use disposable DB/Redis state, while browser integration uses separate local application accounts.

''' + '\n'.join(commands) + '''

Additional artifact copies used `docker compose cp` from distinct `/tmp/mvp-improvement` paths. They do not alter original audit evidence. `backend-full.xml`, `backend-final.xml`, `strict-final.xml`, `original-short.xml` and `original-full.xml` provide test-level records. `release-validation/` contains the final full-suite strict status/duration/terminal reply and pool event measurements; `strict-final/` and `final/` retain preceding passing snapshots. `results.json` is the machine-readable A1 summary. New report/capture tooling writes only improvement paths.

## 14. Remaining risks and limitations

This PASS is local A1 stabilization. It does not establish real-model factual quality, semantic embeddings/citations, prompt-injection resistance, production throughput or safe public ingress. AUD-02/03 remain known failures and AUD-04/05/06/07 are untouched. The new runtime image still contains the pre-existing proxy wildcard and in-process document parsers; this task deliberately does not claim their remediation.

Auth/setup gates are process-local; Redis org/conversation caps coordinate across API instances. No physical DB reservation guarantees every possible many-tenant mix. Short burst fixtures and two-tenant fairness do not replace sustained deployment load tests. Some existing CRUD/DNS verification flows can still hold a DB transaction during their own work; the targeted chat service cycles were removed without globally rewriting CRUD.

The remote query subprocess adds startup overhead and uses the unchanged synchronous adapter's transport behavior; a configurable provider requiring custom runtime dependencies/environment must be reviewed before use. No paid live provider was configured. Hard application termination can leave conservative reserved charges requiring provider/DB reconciliation, as documented before A1. Database/Redis outages may prevent immediate cleanup; no automatic refund assumes upstream usage was free. There is no new privacy purge or billing behavior.

## 15. Rollback considerations

No schema migration occurred. Retain messages/usage and do not downgrade the database or delete volumes. There is no Git repository here, so a `git revert` recipe would be misleading. A pre-existing local `acs-audit-runtime` image has ID `sha256:61031b5bc20687abc6d8029a1d6afccbefa6c679c5d08750db2228c09b63190a`; its 94 application Python-file hashes were inspected with networking disabled and matched the pre-A1 snapshot. `rollback-image-hashes.json` records that verification. Keep this immutable image/reference as a controlled local rollback candidate, alongside configuration backups. It is not a complete backup of bind-mounted workspace source or production data.

The built A1 image is `acs-api:mvp-a1-local`; it was built, not externally deployed. A rollback in a separately authorized environment should restore the selected code/image/config consistently, retain conservative usage, and rerun auth/RLS/smoke tests. A source bind mount overrides an image's code: do not assume retagging an image changes the working tree. The pre-A1 image contains the availability defect, so returning it to customer traffic is not a normal recovery strategy; prefer forward repair or controlled admission/unavailability.

## 16. Final decision and stop boundary

**AUD-01: PASS** against the requested local/default-pool capacity, fairness, security, cancellation and resource-reconciliation gates. Full backend: 602 passed/two unrelated failed; 18 A1 tests pass in the final full suite (preceding focused A1-only run: 18 passed); browser: five passed. No unexpected A1 test failure remains in the final runs. No production readiness claim follows.

**Milestone A remains incomplete.** AUD-02–AUD-07 and subsequent milestones were not started. The original overall NOT READY release decision remains. Work stops after these A1 deliverables; no next task, deployment, paid provider or push is initiated automatically.
'''
(root/'AUD-01_IMPLEMENTATION_REPORT.md').write_text(content.strip()+'\n',encoding='utf-8')
(root/'02_PROGRESS_TRACKER.md').write_text('''# MVP improvement progress tracker

Updated: 22 November 2026 (Asia/Colombo). Current authorized execution: Milestone A1 / AUD-01 only.

| Task | Status | Evidence / remaining work |
|---|---|---|
| Section 10 analysis and implementation plan | PASS | `01_IMPLEMENTATION_PLAN.md`; planning completed before source edits. |
| A1 / AUD-01 pool starvation | PASS (local validation) | `AUD-01_IMPLEMENTATION_REPORT.md`; baseline reproduced; final 18 A1 tests passed, 602 backend passes plus two unrelated failures, five browser passes. |
| A2 / AUD-02 citations | FAIL / NOT_IMPLEMENTED remediation | Original deterministic citation regression still fails; no implementation changes. |
| A3 / AUD-03 provider transport | FAIL / NOT_IMPLEMENTED remediation | Original production HTTP embedding regression still fails; no implementation changes. |
| A4 / AUD-04 proxy trust | NOT_IMPLEMENTED remediation | Existing wildcard runtime trust remains; actual deployment security unverified. |
| A5 / AUD-05 parser isolation | NOT_IMPLEMENTED remediation | Existing parser/worker isolation gap remains. |
| A6 / AUD-06 inbox | NOT_IMPLEMENTED remediation | Existing placeholder remains. |
| A7 / AUD-07 widget lifecycle | NOT_IMPLEMENTED remediation | Existing duplicate-init/teardown gap remains. |
| Milestones B–J | NOT_IMPLEMENTED in this improvement work | Not authorized by the current task; no paid providers/deployment/feature expansion. |

Milestone A completion gate: **NOT COMPLETE**. Overall MVP decision: **NOT READY**, unchanged. A1 PASS is not a full-suite-green or release-ready claim.

All original audit reports/evidence are preserved. This workspace has no `.git`; modified-file evidence uses hashes. The new evidence directory is `evidence/AUD-01/`; see `results.json` and recorded logs/XML for exact commands, failures, reruns and timing. No acceptance thresholds were reduced. Early capacity/latency failures are retained, not overwritten as successes.

Next work requires a separate explicit instruction selecting another task. Stop after A1 reporting; do not automatically begin A2.
''',encoding='utf-8')
print(json.dumps({'reports_created':2,'backend':counts['backend-full'],'new_tests':counts['strict-final'],'audit_changed':audit_changed,'decision':'PASS'}))
