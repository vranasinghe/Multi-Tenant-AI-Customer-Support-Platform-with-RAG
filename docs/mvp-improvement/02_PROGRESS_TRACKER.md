# MVP improvement progress tracker

Updated: 26 November 2026 (Asia/Colombo). Last authorized execution: Milestone A final consolidated stabilization; complete. See `MILESTONE_A_FINAL_REPORT.md`.

| Task | Status | Evidence / remaining work |
|---|---|---|
| Section 10 analysis and implementation plan | PASS | `01_IMPLEMENTATION_PLAN.md`; planning completed before source edits. |
| A1 / AUD-01 pool starvation | PASS (local validation; preserved) | Original report/evidence unchanged; all 18 tests pass in the A3 final full run and isolated rerun. Two intermediate full runs missed P95 by 4.02/11.51 ms; retained as timing risk. Only loopback fixture opt-ins changed; assertion reverse-hash matches. |
| A2 / AUD-02 citations | PASS (local deterministic validation; preserved) | Original report/evidence, implementation and tests unchanged; all 32 tests and original omission regression pass in A3 final full run. Semantic citation quality remains BLOCKED. |
| A3 / AUD-03 provider transport | PASS (local transport validation) | `AUD-03_IMPLEMENTATION_REPORT.md`; original failure reproduced then passes unchanged. 159 new tests pass; final backend 795 pass / zero fail/skip; static checks, final runtime build/RLS and five browser tests pass. Browser routing/cookie harness failures retained. Earlier A1 timing failures retained; no gate relaxed. |
| A4 / AUD-04 proxy trust | PASS (local validation; production ingress BLOCKED) | `AUD-04_IMPLEMENTATION_REPORT.md`; wildcard removed, no peer trusted by default; 197 new unit and 17 runtime-image HTTP cases pass; browser 6/6, smoke, RLS pass. Final backend 1,005 pass / 2 fail / 17 skip, both failures present before A4. |
| A4.1 stabilization | PASS (local) | `A4_1_STABILIZATION_REPORT.md`; full backend 1,016 pass / 0 fail / 17 conditional skips, 17 runtime proxy tests pass separately, browser 6/6, ruff/format/mypy clean. `pnpm format:check` still fails on 8 untouched web files. |
| A5 / AUD-05 parser isolation | PASS (local validation; Linux containers) | `AUD-05_IMPLEMENTATION_REPORT.md`; every parse in a limited child, task limits, enforced worker limits, attempt fencing, per-org admission; 100 new tests; final backend 1,116 pass / 0 fail / 17 conditional skips, 17 runtime proxy tests pass separately, browser 6/6, capacity 10/10. No migration. Crawl limit expiry and a real-worker crawl NOT_TESTED. |
| A5.1 ingestion integrity and crawl validation | PASS (local validation) | `A5_1_INGESTION_INTEGRITY_REPORT.md`; stale-write race reproduced and fixed without a migration; 20 storage tests (3 also on real object storage) and 12 real-worker crawl tests; final backend 1,148 pass / 0 fail / 17 conditional skips, 17 runtime proxy tests pass separately, browser 6/6, capacity 10/10 (worst mixed-crawl margin 103 ms). Production-length crawl limits not waited out. |
| A6.1 PERF-01 stabilization | PASS (local gate) | `A6_1_PERFORMANCE_STABILIZATION_REPORT.md`; 10/10 declared runs, worst P95 1,798 ms; full backend 1,183 pass / 0 fail / 17 conditional skips. 1,600 ms headroom objective not met. |
| A6 / AUD-06 inbox | PASS (local validation; closed by A6.1) | `AUD-06_CLOSURE_REPORT.md`. Original report and its failed run retained. `AUD-06_IMPLEMENTATION_REPORT.md`. Phase 7 inbox already existed; closed pagination, transcript truncation, timestamps, cursor validation, stale data and mobile overflow gaps. No migration. 1,173 pass / 1 capacity fail / 17 skips; web 243; browser 10/10; inbox P95 at most 133 ms on 10,000 conversations. |
| A7 / AUD-07 widget lifecycle | PASS (local validation; Chrome) | `AUD-07_IMPLEMENTATION_REPORT.md`; idempotent install, teardown, instance keys, public response projection; loader 1.1.0 at 5,248 gzip bytes; backend 1,192 pass / 0 fail / 17 conditional skips, browser 17/17, capacity 10/10. |
| Milestone A final stabilization | PASS (local gates); closure pending MIG-02 decision | `MILESTONE_A_FINAL_REPORT.md`; backend 1,209 pass / 0 fail / 17 conditional skips, 17 proxy tests separately, browser 17/17, capacity 10/10 (tightest margin 25 ms), score 80.5 to 85.75. |
| Milestones B–J | NOT_IMPLEMENTED in this improvement work | Not authorized by the current task; no paid providers/deployment/feature expansion. |

## Open observations

| ID | Status | Detail |
|---|---|---|
| PERF-01 | PASS (local gate), thin margin | Cause: one saturated event loop; 10 ms admission polling, plus Phase 7's extra statements. Backoff 10-50 ms. After: 10/10 repetitions pass (max 1,986.81 ms, 13 ms under the gate); final full suite 1,608.6 ms. Earlier failures retained. Watch on slower hardware/CI. |
| PERF-01 (A6.1) | PASS (local gate), host-sensitive | Redundant post-answer cleanup removed; released slots wake waiters. Margin at least 202 ms in declared runs; a throttled host exceeded the gate in both variants of one A/B. |
| WIDGET-PRIV-01 | PASS (confirmed and fixed) | Visitors saw token counts, cost, error codes and citation record ids of their own conversation; now an allowlisted public shape. |
| WIDGET-ERRORS | OPEN, observation | Some public error detail texts are operator-oriented. |
| WIDGET-BROWSERS | OPEN, observation | Resume storage verified in Chrome only. |
| WIDGET-PRIV-01 (as registered by A6.1) | superseded | Public widget history appears to include token counts, estimated cost and internal document and chunk ids. Source inspection only; review in AUD-07. |
| PERF-01 (A6 update) | superseded by A6.1 | 26 November: c100 success P95 2,110 ms in the full suite; alternating A/B 2,020 ms (with AUD-06) and 2,036 ms (without), 1 of 5 each over the 2,000 ms gate. |
| WIDGET-USAGE | merged into WIDGET-PRIV-01 | Public widget history returns token counts, estimated cost and citation ids to visitors. Predates AUD-06. |
| MIG-01 | PASS | Order-dependent test downgrading a shared database; one usage row without a conversation breaks the 0006 foreign key. Tests now own their databases. |
| MIG-02 | DECISION_REQUIRED | Forward-only policy, runbook, restore script, fingerprint check, quiesced pre-upgrade backup and a removable downgrade guard prepared and rehearsed (`docs/RECOVERY.md`). Awaiting approval. |
| LINT-01 | PASS | `ruff check .` clean without exclusions; migration SQL byte-identical. |
| AUD05-STORAGE | PASS (fixed, local) | Crawled originals were overwritten in place. New key per write, published by the owning attempt; unpublished uploads reclaimed through the outbox. |
| AUD05-CRAWL | PASS (validated, local) | Real-worker success, bad pages, soft and hard limits, loss, restart, deletion, duplicates, fencing, retries, fairness. |
| DEVBEAT-CRASH | UNRESOLVED observation | Not reproduced in 4.17 million scheduler ticks; restart policy and health check added. |
| ORG-ORIGINALS | OPEN, observation | Chatbot soft delete keeps originals; an organization row deletion would cascade outbox rows away. Predates A5.1. |
| AUD05-DOCX | OPEN, accept or revisit | A `.docx` with more than about 40 MiB of document XML now fails `parse_resource_limit` (512 MiB parser budget); previously attempted. |
| AUD05-SANDBOX | OPEN | The parser child shares the worker's user, filesystem and network. No seccomp, separate user or egress limit. |
| AUD05-RECOVERY | PASS (local) | Sweep has its own queue and one-slot worker; runs with both ingestion slots busy. |
| OPS-BEAT | PASS (local) | Beat health now means the broker accepted a task recently; consumer health is separate. |
| DEPLOY-01 | OPEN | Set `FORWARDED_ALLOW_IPS` to Caddy's fixed address before production, or all visitors share one IP rate-limit bucket (`DEPLOY_CONTABO.md`). Caddy, ingress denial and TLS unverified. |
| CI-01 | PASS (configuration, scripts run locally); hosted execution NOT_TESTED | `.github/workflows/ci.yml`, `performance.yml`, `scripts/ci/`. |
| FMT-01 | PASS | Working-copy CRLF only: the eight files now equal the committed versions; `format:check` passes. |
| ENV-01 | OPEN | Developer `migrate` image predates 0007; rebuild backend images. |

Milestone A local closure: **pending the MIG-02 decision**; all local engineering gates pass. Overall MVP decision: **NOT READY**, unchanged. Open risks and their dispositions: `MILESTONE_A_RISK_REGISTER.md` (adds RLS-CHECK, BACKUP-OFFSITE, CI-HOSTED, WIDGET-FORGET).

All original audit reports/evidence and completed A1–A3 artifacts are preserved. A1–A3 were recorded when this workspace had no `.git`; it now does. Evidence is separated under `evidence/AUD-01/` to `evidence/AUD-05/`, `evidence/AUD05-STORAGE/`, `evidence/AUD05-CRAWL/` and `evidence/A5.1/`; see recorded logs/XML for exact commands, failures, reruns and timing. No acceptance thresholds or assertions were weakened. Earlier failed attempts are retained, not overwritten as successes.

Stop after the Milestone A final task. Do not begin Milestone B, commit, push or refresh the developer environment without authorization.
