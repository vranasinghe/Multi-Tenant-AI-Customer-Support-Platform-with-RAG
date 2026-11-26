# A4.1 — Regression stabilization and Phase 7 compatibility

Date: 26 November 2026 (Asia/Colombo). Scope: PERF-01, MIG-01, LINT-01 only.

## Decisions

| Item | Decision | Basis |
|---|---|---|
| PERF-01 | **PASS** for the declared local gate, with thin margin | 10 of 10 predeclared repetitions and the final full suite meet every gate |
| MIG-01 | **PASS**, with a recorded compatibility limitation (MIG-02) | Cause verified; isolated and full-suite migration tests pass |
| LINT-01 | **PASS** | `ruff check .` passes with no exclusions; rendered migration SQL byte-identical |
| **A4.1** | **PASS (local)** | All three criteria met |

This is local validation only. Production ingress remains **BLOCKED**, DEPLOY-01 remains **OPEN**, and the MVP remains **NOT READY**.

## 1. Repository and Phase 7 baseline

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`; the AUD-04 work and four earlier user changes were uncommitted. Before changes: SHA-256 inventory of 782 files, patch of uncommitted changes, container inventory and environment flags without values ([preflight](evidence/PERF-01/preflight/preflight.json)). The developer `.env` names a real AI provider with keys; every run here used a disposable Compose project (`acs-a41-qa`) with synthetic credentials, `demo` LLM and `hash` embeddings. No paid call was made.

Compared with the pre-Phase-7 commit `afe3552`, a successful chat send now runs one more `SELECT` and two more conversation `UPDATE`s, and `messages` has a trigram index.

**Current baseline before changes** ([log](evidence/MIG-01/baseline-full-suite.log)): 1,005 passed, 2 failed (`test_strict_capacity[100]` at 2,023 ms; `test_chat_migration_roundtrip`), 17 skipped; Ruff 5 errors.

**Parallel sessions.** Two sessions started from earlier proposals were working on PERF-01 and MIG-01/LINT-01 in the same folder. With the user's approval they were stopped and their disposable containers stopped (not removed). Neither had changed source, test or migration files. The PERF-01 session's five runs are preserved in [baseline-devstack-up](evidence/PERF-01/baseline-devstack-up/): 2,253, 1,994, 2,127, 1,965, 1,942 ms (2 failures). They ran while the other session was running tests, so they are not used for any decision.

## 2. Existing unrelated changes preserved

Frontend, CSS, production Compose, `.prettierignore`, `docs/ui-ux/`, original audits and earlier evidence are unchanged ([artifact validation](evidence/PERF-01/artifact-validation.json)). No reset, clean, commit, push or history change.

The developer containers were stopped and restarted (with authorization) for idle and loaded measurements; volumes untouched. The session's Next.js development server was stopped for the series and restarted for browser tests.

## 3. PERF-01

### Method

Each repetition is a fresh pytest process running the unchanged [capacity file](../../services/api/tests/integration/api/mvp_improvement/test_chat_capacity.py) (concurrency 1, 10, 50, 100 and second-tenant fairness) with real PostgreSQL and Redis. Run count was fixed at five per series before running; every result is kept. Host: 32 logical CPUs, 15.5 GiB for Docker; host CPU and container usage recorded per run. Runner: [perf01_series.py](tools/perf01_series.py).

Three runner start-ups failed before any measurement (`series/baseline-idle`, `series/idle-baseline`, `series/idle-1`, each with `ABORTED.txt`).

### Diagnosis (instrumented runs; not acceptance evidence)

[Probe](tools/perf_probe.py), concurrency 100:

- **One event loop was saturated:** 1,999 ms of loop-thread CPU in a 2,145 ms burst (93%). Latency is queueing for that thread.
- **Admission busy-polling:** a waiting request retried every 10 ms: **3,523 Redis `EVAL` calls** for 100 requests (about 28 per successful, 39 per rejected request). In a [CPU profile](evidence/PERF-01/probe-cpu-breakdown.log), the admission path took about 0.79 s of roughly 3.1 s of profiled loop time.
- **Database not the cause:** [server-side statistics](evidence/PERF-01/pg-statements.log) show about 80 ms total execution for the burst, longest wait 21 ms on the usage advisory lock, no lock wait over 100 ms. `EXPLAIN` plans were not captured: no statement was slow on this small fixture, so behavior with large data is unassessed.
- **Repeated statements** (`set_config` 452, user lookups 142) come from per-transaction RLS context and deliberate re-validation; unchanged.
- **Phase 7 overhead is real:** five [interleaved pairs](evidence/PERF-01/phase7-ab.log), same idle host, concurrency 100:

| Pair | 1 | 2 | 3 | 4 | 5 | median |
|---|---|---|---|---|---|---|
| Before Phase 7 (`afe3552`) | 1,803 | 1,717 | 1,733 | 1,899 | 1,918 | 1,803 |
| Current | 1,949 | 1,906 | 1,935 | 2,118 | 1,947 | 1,947 |

Current code was slower in every pair (28 to 219 ms).

| Phase (successful requests, p50 / p95 ms) | Before fix | After fix |
|---|---|---|
| Authentication slot wait | 750 / 1,172 | 367 / 600 |
| Session lookup | 17 / 37 | 9 / 15 |
| Connection checkout (all in a request) | 12 / 49 | 7 / 38 |
| Preparation, total | 593 / 967 | 662 / 941 |
| Admission (before: Redis call time only; after: whole wait) | 85 / 232 | 619 / 901 |
| Query embedding (local hash) | 0.1 / 0.1 | 0.1 / 0.1 |
| Retrieval | 7 / 25 | 4 / 14 |
| Usage reservation | 4 / 19 | 2 / 9 |
| Commits | 10 / 31 | 7 / 19 |
| Streaming and finalization (fixture provider) | 26 / 87 | 20 / 47 |

Statements per successful request: 37. Transaction duration was not measured separately.

**Verified cause:** the workload is bound by one event loop's CPU; 10 ms admission polling spent a large, avoidable share of it, and Phase 7's extra statements consumed most of the remaining margin under the 2,000 ms gate. Environment noise explains why runs near the gate pass or fail; it is not the whole story.

### Remediation

`chat_controls.admit()` replaces the loop in `conversations._prepare`: retries after 10, 20, 40 then 50 ms, never sleeping past the window, with a last attempt as it closes. Unchanged: 0.9 s window, cap of three per organization, pool 5+5, 2 s pool timeout, setup and authentication limits, `429 chat_busy`, usage reservation, persistence, SSE. Phase 7 writes were left as they are. Six unit tests ([red](evidence/PERF-01/admission-red.log), [green](evidence/PERF-01/admission-green.log)).

Instrumented effect: `EVAL` 3,523 → 1,647; loop CPU 1,999 → 1,606 ms; successful requests 42 → 59.

Trade-off: a slot freed during a wait can now stay free for up to about 50 ms (was 10 ms), and a new arrival polls faster than an older waiter for its first 70 ms.

### All repetitions

Successful P95 in ms; at 50 and 100: (success / rejected / unexpected).

**Before — idle host** (developer stack stopped)

| Run | c1 | c10 | c50 | c100 | rejected P95 c100 | host CPU % | result |
|---|---|---|---|---|---|---|---|
| 1 | 43 | 304 | 1200 (43/7/0) | 1918 (39/61/0) | 1733 | 13.3 | pass |
| 2 | 49 | 274 | 1373 (36/14/0) | 1976 (38/62/0) | 1672 | 19.1 | pass |
| 3 | 50 | 271 | 1270 (41/9/0) | 1883 (36/64/0) | 1745 | 12.6 | pass |
| 4 | 64 | 256 | 1241 (42/8/0) | 1880 (43/57/0) | 1803 | 15.0 | pass |
| 5 | 39 | 226 | 1126 (46/4/0) | 1700 (43/57/0) | 1580 | 11.8 | pass |

**Before — developer stack up**

| Run | c1 | c10 | c50 | c100 | rejected P95 c100 | host CPU % | result |
|---|---|---|---|---|---|---|---|
| 1 | 50 | 280 | 1173 (43/7/0) | 1756 (41/59/0) | 1592 | 14.3 | pass |
| 2 | 41 | 281 | 1177 (41/9/0) | 1960 (47/53/0) | 1657 | 14.8 | pass |
| 3 | 58 | 282 | 1326 (33/17/0) | 1844 (42/58/0) | 1615 | 17.8 | pass |
| 4 | 58 | 270 | 1230 (36/14/0) | 1711 (38/62/0) | 1601 | 11.5 | pass |
| 5 | 53 | 421 | 1440 (31/19/0) | **2246** (40/60/0) | 2007 | 12.1 | **FAIL** |

**After — idle host**

| Run | c1 | c10 | c50 | c100 | rejected P95 c100 | host CPU % | result |
|---|---|---|---|---|---|---|---|
| 1 | 38 | 256 | 1077 (47/3/0) | 1547 (54/46/0) | 1486 | 13.1 | pass |
| 2 | 42 | 276 | 1287 (41/9/0) | 1987 (46/54/0) | 1822 | 10.4 | pass |
| 3 | 56 | 338 | 1295 (39/11/0) | 1944 (44/56/0) | 1553 | 16.0 | pass |
| 4 | 54 | 281 | 1064 (47/3/0) | 1865 (40/60/0) | 1621 | 10.8 | pass |
| 5 | 53 | 284 | 1162 (45/5/0) | 1625 (42/58/0) | 1456 | 15.8 | pass |

**After — developer stack up**

| Run | c1 | c10 | c50 | c100 | rejected P95 c100 | host CPU % | result |
|---|---|---|---|---|---|---|---|
| 1 | 59 | 286 | 1178 (45/5/0) | 1824 (43/57/0) | 1549 | 16.4 | pass |
| 2 | 49 | 283 | 1201 (44/6/0) | 1727 (35/65/0) | 1515 | 21.1 | pass |
| 3 | 56 | 329 | 1183 (43/7/0) | 1706 (43/57/0) | 1597 | 16.1 | pass |
| 4 | 50 | 283 | 1212 (41/9/0) | 1834 (48/52/0) | 1519 | 17.9 | pass |
| 5 | 48 | 323 | 1340 (45/5/0) | 1741 (49/51/0) | 1624 | 22.6 | pass |

| c100 series | median | min | max | failed runs |
|---|---|---|---|---|
| Before, idle | 1,883 | 1,700 | 1,976 | 0 of 5 |
| Before, dev stack up | 1,844 | 1,711 | 2,246 | 1 of 5 |
| After, idle | 1,865 | 1,547 | 1,987 | 0 of 5 |
| After, dev stack up | 1,741 | 1,706 | 1,834 | 0 of 5 |

Every run: no unexpected failure, stream failure or timeout; full overlap; no outstanding or unbalanced checkout (peak at most 10); rejected P95 at most 2,007 ms; success floors, fairness, lease and permit cleanup and persisted messages/usage asserted by the test.

**Final full suite:** concurrency 100 P95 **1,609 ms** (56 / 44 / 0).

### Residual risk — read before relying on this

- Across ten runs each, the median moved from about 1,882 to 1,782 ms (5%), much smaller than the instrumented run suggests, and run-to-run spread is larger than the gain. Successful requests rose from 407 to 444.
- The worst run after the fix was 1,987 ms, **13 ms under the gate**. A later failure is plausible, especially on slower hardware such as a CI runner, which was not measured.
- The cheapest next margin, if needed, is Phase 7's extra send-path statements (for example merging the added `SELECT` into its `UPDATE`). Not done: the gate is met and this checkpoint asks for the smallest change.

## 4. MIG-01

**Reproduction:** passes [alone](evidence/MIG-01/isolated-test.log); fails in the full suite; [minimized](evidence/MIG-01/minimized-sequence.log) to two tests: `test_delete_keeps_usage_and_retention_is_org_scoped`, then the round-trip.

**Exact error:** `psycopg.errors.ForeignKeyViolation` on `chat_usage_org_id_conversation_id_fkey` while `0007`'s downgrade re-adds the key. [Data just before](evidence/MIG-01/baseline-mig-state.json): revision `0007`, 354 usage rows, **exactly 1** without a conversation, in 1 organization.

**Verified cause:** Phase 7 deliberately drops that foreign key so usage survives conversation deletion and retention purge. The 0006 schema cannot represent such a row. The data is valid; the downgrade is incompatible with it. The test met it only because it downgraded the session's shared database, which also made its own downgrade to `0004` destructive to other tests' data.

**Persistent databases:** `0007` is applied to the developer database ([check](evidence/MIG-01/persistent-database-revisions.log)) and the commit is on `origin`. It is treated as published: no behavior of the migration was changed. No deployed database is known.

**Correction:** the round-trip keeps its assertions and runs on its own disposable database. No data is deleted, no constraint disabled. Three tests added on seeded data (two organizations, playground and widget conversations, messages, widget sessions, usage, vectors):

- upgrade `0006 → head`: rows, usage and vectors unchanged; inbox fields backfilled; FORCE RLS and tenant isolation hold; no unvalidated constraint;
- supported downgrade to `0006` and re-upgrade: core rows and usage unchanged; Phase 7 tables removed;
- after a conversation deletion: downgrade **fails as a whole**; revision, usage and analytics rows unchanged.

They characterize existing behavior, so they passed once the seed data was valid (two earlier attempts failed on my seed's type and key format; logs kept).

### MIG-02 — compatibility limitation (open, needs your decision)

1. Once any conversation has been deleted, downgrading below `0007` is impossible without discarding usage records. It fails safely.
2. Even when it succeeds, the downgrade **drops Phase 7 data** (events, unanswered questions, daily analytics, export records, conversation status/CSAT/handoff fields, latency) with no warning.

Proposed policy, **not implemented**: treat `0007` as forward-only on any database with real data; recover with a forward fix, or restore a backup taken before the migration. Optionally, in a reviewed change, make the downgrade refuse with a clear message when Phase 7 data exists.

## 5. LINT-01

Four long lines split by implicit string concatenation; the one flagged f-string now writes the constant role name literally, so no suppression was added (an existing `noqa` elsewhere in the file is unchanged). Offline SQL for upgrade and downgrade is **byte-identical** [before](evidence/LINT-01/migration-0007-before.sql) and [after](evidence/LINT-01/migration-0007-after.sql).

## 6. Modified files

- Application: `app/services/chat_controls.py` (`admit`), `app/services/conversations.py`.
- Migration: `20261125_0007_conversation_analytics.py` (formatting only).
- Tests: `tests/integration/test_chat_migration.py`, `tests/support/database.py` (`temporary_database`), new `tests/unit/mvp_improvement/test_chat_admission.py`.
- Documentation: `docs/CHAT_ENGINE.md`, progress tracker, this report; tools `capture_a41.py`, `perf01_series.py`, `perf_probe.py`, `mig_probe.py`, `verify_a41.py`.

## 7. Final validation

| Check | Result |
|---|---|
| Full backend suite with live ingestion | **1,016 passed, 0 failed, 17 skipped** (156.82 s) |
| Runtime proxy tests (the 17 skips), runtime image `acs-api:mvp-a41-local` | **17 passed** |
| `ruff check .`, `ruff format --check .`, strict `mypy` | pass, 189 files, 187 sources ([log](evidence/LINT-01/static-final-2.log)) |
| FORCE RLS; Alembic head and current | no unprotected tables; `0007` |
| Smoke; Playwright | all checks passed; **6 passed** |
| Web ESLint, type check, Vitest; widget tests | pass; 220 passed; 7 passed |
| `pnpm format:check` | **FAIL**: 8 web component files, all unchanged from HEAD ([list](evidence/LINT-01/prettier-files.log)); not touched. CI runs this check. |

Browser and smoke tests used the Next.js development server. The web production build was not run. Static checks first failed on type and format errors in the new tests; those logs are kept.

### Security preservation (final full run)

| Group | Tests | Failures |
|---|---|---|
| AUD-01 | 18 | 0 |
| AUD-02 | 32 | 0 |
| AUD-03 | 159 | 0 |
| AUD-04 unit (plus 17 runtime, above) | 197 | 0 |
| Original audit regressions (unit 2, implementation 2) | 4 | 0 |
| Auth, route permissions, tenant isolation | 65 | 0 |
| Widget | 12 | 0 |
| Phase 7 analytics | 13 | 0 |
| Conversations | 19 | 0 |

No change to citation, provider-transport, proxy-trust, origin, capability or rate-limit code.

## 8. CI coverage gap (proposal only)

`ci.yml` builds the runtime image but never runs the 17 proxy tests, and does not run Playwright. The `api` job runs the capacity gate on a shared runner, which may be flaky. Proposed for the Milestone A completion gate, in the `stack` job: add `load: true` to the image build step (so `docker run` can use `acs-api:ci`), set up `uv`, and after the stack starts:

```yaml
- name: Runtime proxy trust tests (AUD-04)
  working-directory: services/api
  env:
    RUNTIME_PROXY_IMAGE: acs-api:ci
    RUNTIME_PROXY_STACK_NETWORK: ai-chatbot-saas_default
    RUNTIME_PROXY_REDIS_CONTAINER: ai-chatbot-saas-redis-1
    RUNTIME_PROXY_DATABASE_URL: postgresql+psycopg://platform_app:change-me-local-app@postgres:5432/chatbot
  run: uv sync --locked && uv run pytest tests/integration/test_runtime_proxy_trust.py
```

Not applied and not tried on a runner.

## 9. Deployment risks

- **DEPLOY-01 open.** No proxy address was guessed, no trusted range widened, no wildcard restored.
- Not verified: Caddy header sanitation, direct-ingress denial, TLS termination, production load.
- Existing developer containers still start from their old images (`uvicorn` directly) until rebuilt.
- **Stale `migrate` container (cause found):** its image was built before `0007` was committed and the service has no source mount, so it holds only `0001`–`0006` and exits with `Can't locate revision '0007'` ([evidence](evidence/MIG-01/stale-migrate-image.log)). This also makes `docker compose start` stop early. Expected remedy: `docker compose build migrate storage-init api worker beat`; **not run here**.
- Admission polling and capacity are per process; behavior with several API instances and a real provider is unmeasured.

## 10. Rollback

No schema or data change. Reverting `admit()` restores 10 ms polling. The migration edit has no database effect. Reverting the test changes would bring back the order-dependent failure. See MIG-02 before downgrading any database.

## Stop boundary

AUD-05 to AUD-07, Milestones B–J and new Phase 7 features were not started. Nothing was committed, pushed or deployed.
