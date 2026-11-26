# A6.1 — Recurring PERF-01 investigation and AUD-06 closure

Date: 26 November 2026 (Asia/Colombo). Scope: the chat capacity gate only.

## 1. Baseline and environment

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`, with the uncommitted A1–A6 and earlier user work. Before any edit: SHA-256 inventory of 1,565 files and patch ([preflight](evidence/PERF-01-A6/preflight/preflight.json)). Only this session changed files. A disposable stack (`acs-a61-qa`) with synthetic credentials, `demo` LLM and `hash` embeddings; developer services untouched; no paid call.

Host: i9-13900HX laptop (performance and efficiency cores), 32 logical CPUs, 15.5 GiB for Docker, on AC power. A fixed single-thread loop in the API container took 30–51 ms at different moments ([calibration](evidence/PERF-01-A6/baseline/calibration.log)); every series records it per run.

**Reproduction, unchanged code, five declared runs:** c100 successful P95 1,693 / 1,736 / 1,772 / 1,937 / 1,950 ms (median 1,772), no failure ([series](evidence/PERF-01-A6/series/baseline-5/summary.json)). The A6 failures (2,110 ms in the full suite; 2,020 and 2,036 ms in its A/B) were not reproduced here, but the spread leaves as little as 50 ms.

## 2. Diagnosis

Instrumented runs, not acceptance evidence ([probe](evidence/PERF-01-A6/profile/timing/), [CPU profile](evidence/PERF-01-A6/profile/cpu/), [statement trace](evidence/PERF-01-A6/profile/statement-trace.log)):

| Finding at c100 | Value |
|---|---|
| Event-loop thread CPU / burst wall | 1,850 / 2,091 ms (89%) |
| Loop scheduling lag P95 / max | 8.8 / 68.9 ms |
| Authentication slot wait, successful requests P50 / P95 | 743 / 1,127 ms |
| Admission wait P50 / P95 | 562 / 902 ms |
| Redis `EVAL` calls | 1,358 |
| Statements per successful send | 37 |
| Retrieval, embedding, quota reservation P95 | 20, 0.2, 18 ms |
| Database pool peak | 8–9 of 10 |

**Verified:** latency is queueing for one saturated event loop; database execution is not the limit. Two avoidable costs on it:

1. **A second cleanup after every successful answer.** `close_pending_turn` always opened a new transaction (connection checkout, tenant context, two updates matching nothing, commit) and released the already released lease.
2. **Admission polling.** Waiting requests still polled Redis every 50 ms, and a freed slot stayed empty until the next poll.

A4.1's other finding, extra Phase 7 statements, still holds in a small way (a re-read plus update of the conversation); it was not changed. The self-time profile is spread over SQLAlchemy, psycopg, FastAPI and Redis; its cumulative figures are distorted by greenlet switching and were not used.

**Not established:** why A6-era runs and some runs here were much slower. During the second A/B every run of both variants measured 2,153–2,651 ms while the same calibration rose from 38 to 49 ms and the CPU's performance counter fell from about 218% to 163–181%. Throttling is consistent with that, but not proven.

## 3. Remediation (two iterations, the limit)

**Iteration 1 — clean up only what is left.** The stream marks its turn `finalized` after the commit and `released` after the lease release; cleanup does each only if unmarked. A failed finalization, failed release, client disconnect or never-started stream behave as before.

**Iteration 2 — hand over released slots.** A release wakes the oldest waiter of that organization in the process; polling is only the fallback and now backs off from 10 to 200 ms (was 50). A woken waiter that is cancelled passes the hint on.

Unchanged: 0.9 s window, three concurrent chats per organization, pool 5+5 and 2 s timeout, setup and authentication limits, Lua scripts, error codes, authorization revalidation, RLS, citations, usage reservation and charging, SSE. No schema change.

**Trade-off:** a slot freed by another process or by expiry can now be picked up after up to 200 ms instead of 50. The API runs as a single process; adding API processes would make this matter.

Not done, deliberately: removing context or authorization statements, disabling connection pre-ping, merging Phase 7 writes (small gain, more risk).

## 4. Files

`services/api/app/services/conversations.py`, `app/services/chat_controls.py`; new tests `tests/integration/api/mvp_improvement/test_chat_turn_cleanup.py` (4), `tests/unit/mvp_improvement/test_chat_admission_wake.py` (5). No existing test or assertion changed. Tools `docs/mvp-improvement/tools/*_a61.py`; `CHAT_ENGINE.md` (admission wait), this report, the closure record and the tracker. Preservation and secret scan: [artifact validation](evidence/PERF-01-A6/artifact-validation.json), no protected file changed and no finding.

Test first: iteration 1 [1 failed, 3 passed](evidence/PERF-01-A6/fix1/red.log) (the three are behaviour that had to survive); iteration 2 [5 of 5 failed](evidence/PERF-01-A6/fix2/red.log).

## 5. Effect of each iteration

Alternating A/B, five pairs each, every run kept.

| Series | After: median P95 / successes | Before: median P95 / successes | Reading |
|---|---|---|---|
| [Iteration 1](evidence/PERF-01-A6/series/fix1-ab-5/summary.json) | 1,712 / 48 | 1,746 / 53 | within noise; faster in 3 of 5 pairs. Probe loop CPU 1,850 → 1,600 ms |
| [Iteration 2](evidence/PERF-01-A6/series/fix2-ab-5/summary.json) | 2,299 / 40 | 2,573 / 38 | **all ten runs over the gate** (host slowdown); iteration 2 faster in 4 of 5 pairs. Probe `EVAL` 1,608 → 868 |

## 6. Acceptance

Declared with frozen source hashes before running ([plan](evidence/PERF-01-A6/acceptance-plan.json)), after the calibration had returned to its starting level. No run repeated or removed.

| Series, c100 | P95 ms per run | Median / min / max | Successes (of 100) | Rejected | Throughput /s | Failed runs |
|---|---|---|---|---|---|---|
| [Before any change](evidence/PERF-01-A6/series/baseline-5/summary.json) | 1,693 / 1,736 / 1,772 / 1,937 / 1,950 | 1,772 / 1,693 / 1,950 | 56 45 40 46 48 | 44–60 | 20–31 | 0 |
| [Unloaded](evidence/PERF-01-A6/series/accept-unloaded-5/summary.json) | 1,748 / 1,798 / 1,790 / 1,765 / 1,743 | 1,765 / 1,743 / 1,798 | 62 57 57 61 67 | 33–43 | 30–36 | 0 |
| [With crawling](evidence/PERF-01-A6/series/accept-crawl-5/summary.json) | 1,732 / 1,685 / 1,768 / 1,709 / 1,707 | 1,709 / 1,685 / 1,768 | 61 60 59 62 60 | 38–41 | 31–34 | 0 |

Every run met every gate at 1, 10, 50 and 100 (genuine overlap, no unexpected 500 or stream failure, no harness timeout, floors, rejection P95 at most 1,762 ms, second-tenant fairness, balanced pool, no leaked lease or permit, stored messages and usage). Crawl load: 32 crawls, 384 page publications, no failure.

- At concurrency 50 all 50 requests now succeed (38–44 before). P95 at c50 about 1,200 ms (about 1,300 before).
- Containers during the series were near idle apart from the one under test (per-run snapshots in each summary); host CPU before runs 3–26%.
- **Margin below the 2,000 ms gate: at least 202 ms** in these series.
- **Headroom objective (median at most 1,600 ms): not met** (1,765 ms). P95 stayed level while about 30% more requests completed.

### Four-CPU experiment

API, PostgreSQL and Redis pinned to CPUs 0–3, three declared-as-experiment runs ([data](evidence/PERF-01-A6/series/vcpu4-3/summary.json)): P95 1,583 / 1,609 / 1,637 ms, 60–65 successes, all gates met. Faster than with 32 CPUs, which suggests that scheduling of the single loop across virtual CPUs matters on this host. These are laptop cores of unknown type, with the load generator inside the API process: **not** a latency promise for a 4-vCPU server.

## 7. Regression

| Check | Result |
|---|---|
| Full backend suite with live ingestion | **1,183 passed, 0 failed, 17 skipped**, 778 s; capacity inside it: c100 59 successes, P95 1,685 ms ([log](evidence/PERF-01-A6/full/backend-full.log), [JUnit](evidence/PERF-01-A6/full/backend-full.xml)) |
| Runtime proxy tests (the 17 skips), image `acs-api:mvp-a61-local` | 17 passed |
| `ruff check`, `ruff format --check`, strict `mypy` | pass ([log](evidence/PERF-01-A6/static/second.log); the [first run](evidence/PERF-01-A6/static/first.log) flagged formatting in a new test) |
| Runtime Docker build; production web build | pass |
| Alembic head / current; FORCE RLS | `0007` / `0007`; no unprotected tables |
| Web / widget unit tests; ESLint; type check | 243 / 7 passed; pass; pass |
| `pnpm format:check` | **FAIL**, the same 8 files (FMT-01, open) |
| Smoke; Playwright, all specs, sign-up limit unchanged | pass; 10 of 10 on a fresh stack |
| CI | NOT_TESTED |

Every preservation group passes: AUD-01 18, AUD-02 32, AUD-03 159, AUD-04 197 plus 17 runtime, A4.1 admission and migration 15 (including the 5 new wake tests by name), auth/RBAC/isolation 89, widget 12, analytics 13, conversations 19, AUD-05 100, A5.1 32, AUD-06 inbox 26, new A6.1 tests 9 ([groups](evidence/PERF-01-A6/full/groups.log)). The nine new tests are counted once.

## 8. WIDGET-PRIV-01

Registered as a **source-inspection observation requiring runtime verification**: `GET /public/v1/chat` returns messages in the dashboard's shape, which includes token counts, estimated provider cost, and citation `document_id` and `chunk_id`. Not changed here. Recommended for the separately authorized AUD-07 widget lifecycle task.

## 9. Limitations and rollback

- Local evidence from one laptop; the load generator shares the API's event loop, so figures include it.
- The gate was exceeded by both variants during a host slowdown. A slow or throttled machine can still fail it; CI hardware is untested (CI-01).
- Admission order is approximately first-come within one process; new arrivals can still take a freed slot first, as before.
- Rollback: revert the two service files. No data, schema or contract change.

## 10. Decisions

**PERF-01: PASS for the declared local gate**, with a recorded sensitivity: 10 of 10 declared acceptance runs, the full suite and the four-CPU runs pass; margin at least 202 ms; the 1,600 ms headroom objective is not met; a throttled host has been seen to exceed the gate with or without these changes.

**AUD-06: PASS for local validation** — see the [closure record](AUD-06_CLOSURE_REPORT.md).

Milestone A is not complete (AUD-07 and open observations remain). **Overall MVP: NOT READY.** Nothing was committed, pushed or deployed, and no paid provider call was made.
