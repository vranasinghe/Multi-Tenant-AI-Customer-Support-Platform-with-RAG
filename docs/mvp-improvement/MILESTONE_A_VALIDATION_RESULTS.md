# Milestone A validation results

26 November 2026, Asia/Colombo. Developer laptop (i9-13900HX), Docker Desktop, Linux containers,
disposable Compose projects with synthetic credentials, `demo` LLM and `hash` embeddings. No paid
call, no deployment, nothing committed.

Evidence: [evidence/MILESTONE-A-FINAL](evidence/MILESTONE-A-FINAL/). Each file under `final/` has a
`.json` with the exact command, exit code and duration.

## Baseline (before any change)

Run from a copy of the starting snapshot: **1,191 passed, 1 failed, 17 skipped** (785 s). The
failure was this task's QA setup (shifted web port, so the live test's default origin was refused
with `origin_not_allowed`); the same test [passed](evidence/MILESTONE-A-FINAL/baseline/live-ingestion-rerun-correct-origin.log)
with the right origin. Capacity c100 in that run: 66 served, success P95 1,699 ms.
`pnpm format:check`: failed on 8 files.

## Final run (source frozen: 439 files, [unchanged afterwards](evidence/MILESTONE-A-FINAL/final/freeze.json))

| Gate | Result |
|---|---|
| Full backend suite, live ingestion, capacity gate included | **1,209 passed, 0 failed, 17 skipped**, 855 s. All 17 skips are the runtime proxy tests |
| Runtime image build and proxy tests (host) | **17 passed, 0 skipped** |
| Ruff, Ruff format, strict mypy | PASS (215 files; 213 checked by mypy) |
| `pnpm format:check` (whole repository, no new exclusions) | **PASS** |
| ESLint, TypeScript | PASS |
| Widget unit; web unit | 19; 243 passed |
| Widget and web production builds | PASS; loader 5,248 gzip bytes of 10,240 |
| Widget bundle: Linux build equals committed bytes | PASS (`567672…2e6`) |
| Smoke; browser journeys (installed Chrome) | PASS; **17 of 17** |
| Alembic heads/current; empty-database downgrade and upgrade | `0007`/`0007`; PASS |
| FORCE RLS | PASS, no unprotected table (see RLS-CHECK for its limits) |
| Backup and restore rehearsal | PASS |
| Preservation and secrets | No protected file changed, nothing removed, [no secret found](evidence/MILESTONE-A-FINAL/artifact-validation.json) |

The first final web command failed (`MODULE_NOT_FOUND`) because the capture wrapper's
`MSYS_NO_PATHCONV` breaks `corepack` on Windows; both logs are kept (`web.log`, `web-2.log`).

Unit tests alone on Linux, as the CI static job runs them: 753 passed, 0 skipped.

## Capacity

[Declared before running](evidence/MILESTONE-A-FINAL/perf-plan.json). Workload, thresholds and
fairness assertions unchanged (the test file is byte-identical to the starting snapshot). Gates:
c100 success P95 ≤ 2,000 ms, rejection P95 ≤ 3,000 ms. Every run is listed.

| Series | c100 success P95 ms, runs 1–5 | Rejection P95 ms | Served of 100 | Failed runs |
|---|---|---|---|---|
| [Unloaded](evidence/MILESTONE-A-FINAL/perf/unloaded-5/summary.json) | 1,625 / 1,701 / 1,735 / 1,649 / 1,606 | 1,583–1,738 | 63–67 | 0 |
| [With crawling](evidence/MILESTONE-A-FINAL/perf/mixed-crawl-5/summary.json) | **1,975** / 1,680 / 1,699 / 1,772 / 1,776 | 1,683–1,928 | 54–64 | 0 |

**The first mixed run passed with only 25 ms to spare.** Host calibration was among the slowest of
the ten in that run (38.3 ms; range 31.2–39.7). Crawl load: 34 crawls, 408 pages, no failures.
This certifies this laptop at those moments, not any target server (PERF-01).

## Scheduler and recovery

| Check | Observed | Where |
|---|---|---|
| Sweep runs with both ingestion slots busy; stuck job recovered and abandoned object purged | 1.7 s (bound 15 s with a 5 s test interval); 2.2 s in an earlier run | `final/suite-data/maintenance-busy-slots.json` |
| Same test with the sweep routed to `default` again | **Timed out** (red state) | `scheduler/red-guard-and-routing.log` |
| Beat health: healthy after first publish; unhealthy after beat stops; consumer unaffected | PASS | `test_maintenance_worker.py` |
| Consumer health: unhealthy when it does not answer | PASS | same |
| Failed publish records no progress | PASS, unit level with a simulated broker error | `test_maintenance_scheduling.py` |
| Hard-killed jobs recovered within bound | Documents 30.7 s, crawls 32–33 s (bound 40 s, test timings) | `final/suite-data/` |
| Stale attempts publish nothing; tenant isolation and limits | Existing suites pass | full run |
| Health checks in the running stack | `beat`, `maintenance`, `worker` healthy after the 20-minute suite | live `compose ps` |
| Maintenance memory | about 150 MB of a 512 MB limit | `scheduler/memory.log` |

Production defaults give a recovery bound of about 17 minutes (900 s stuck + 120 s interval); that
duration itself was not waited out. A recovered job still waits for a free slot to *run*.
Overlapping sweeps are harmless by design (claims and idempotent deletes) and untaken sweeps
expire; two `beat` instances were not tested and must not be run.

**DEVBEAT-CRASH:** 4,173,843 accelerated ticks of the real persistent scheduler
[did not reproduce it](evidence/MILESTONE-A-FINAL/scheduler/devbeat-reproduction-attempt.log).

## Backup and restore rehearsal

Real `deploy/backup.sh` (quiesced) and `deploy/restore.sh` into a new project, compared with
`verify-data`: **identical** counts and hashes for every table (vectors included), RLS flags,
policies, grants, functions, constraints, indexes, and 6 of 6 stored originals; then the restored
application served the same sign-in, transcript, retrieval results and inbox. A second restore onto
the populated copy was refused. Final run data: 22 conversations, 32 messages, 17 usage rows, 6
chunks; backup 3 s, restore and verify 25 s. **Tiny synthetic data: no recovery-time claim.**

Two earlier attempts failed and are kept:

1. `restore.sh` treated a new document volume as non-empty (the storage image ships a folder).
2. **The restored database had `DELETE` grants the source had revoked**: the new database's default
   privileges applied to every recreated table. The previously documented `psql` restore had the
   same flaw. Fixed in `restore.sh`; the same run also showed a failed `diff` did not stop the
   script, now fixed.

Not covered: live conversation exports (none in the data), roles beyond `platform_app`,
production Compose file (it refuses offline providers), off-server copies.

## CI

| Item | Status |
|---|---|
| Workflows `ci.yml`, `performance.yml` | Written; YAML parses, actions pinned by commit, scripts exist ([log](evidence/MILESTONE-A-FINAL/static/workflow-validation.log)) |
| `migrations.sh`, `runtime-proxy.sh`, `restore-rehearsal.sh`, `browser.sh`, `up.sh` | Run locally, pass |
| `backend-suite.sh` | Run locally with `--with-capacity`; CI runs it without that file |
| `capacity.sh`, `make-env.sh` | `make-env.sh` used; `capacity.sh` itself not run (the series tool ran the same test) |
| `actionlint`, `shellcheck` | Not installed: NOT_TESTED |
| Playwright with bundled Chromium (CI's browser) | NOT_TESTED |
| **Execution on GitHub** | **NOT_TESTED: requires a push you have not authorized** |

## Skips, and what was not tested

17 conditional skips, all executed separately. NOT_TESTED: hosted CI; real AI providers; other
browsers; production Compose, ingress, TLS and server; production-length recovery and crawl limits;
production-sized restore; developer-environment refresh.

## Developer environment

Not restarted, rebuilt or modified. After the work: `api` healthy (`/readyz` 200, no traceback in
four hours of log), `worker` still running old code, `beat` still exited. The developer `api`
reloads source from the working tree, so it now runs the new API code; nothing it publishes
changed queue. See ENV-01 before refreshing.
