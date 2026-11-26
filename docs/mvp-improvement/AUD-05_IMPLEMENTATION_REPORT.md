# AUD-05 — Document parser resource isolation and worker recovery

Date: 26 November 2026 (Asia/Colombo). Scope: Milestone A5 / AUD-05, Section 10 of the approved implementation plan.

## 1. Executive summary

**AUD-05: PASS for local validation** on Linux containers. Every PDF, DOCX, TXT and HTML parse now runs in a fresh, resource-limited child process; ingestion tasks have time limits; the worker has enforced memory, CPU and PID limits; a superseded or killed attempt can no longer change anything; and one organization cannot occupy both worker slots. These were exercised with real child processes, a real prefork Celery worker that was killed and restarted, and kernel-level limits, not only configuration.

Final run: **1,116 passed, 0 failed, 17 conditional skips** (the 17 runtime proxy tests, which also pass separately); Ruff, format and strict mypy clean; browser 6/6; smoke, FORCE RLS and ten of ten strict capacity repetitions pass.

Read with the decision:

- It is **resource containment, not a security sandbox** (section 18).
- A `.docx` with more than about **40 MiB of document XML now fails**, where it was attempted before (section 7).
- Crawl task time limits are configured and reported by a real worker, but their **enforcement was not exercised**; a website crawl was not run through a real prefork worker.
- With default settings, recovery from a hard-killed job takes **up to about 17 minutes**.
- Nothing was deployed; production ingress stays **BLOCKED**, CI-01 stays open. **The MVP remains NOT READY.**

## 2. Repository baseline

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`, with the uncommitted AUD-04 and A4.1 work plus earlier user changes. Before any edit: SHA-256 inventory of 1,054 files, patch of uncommitted changes, container inventory and environment flags without values ([preflight](evidence/AUD-05/preflight/preflight.json), [hashes](evidence/AUD-05/preflight/before_hashes.json), [patch](evidence/AUD-05/preflight/pre_existing_uncommitted.patch)). No other session was running. No commit, push, reset, clean or history change.

**Test environment.** The developer `.env` names a real AI provider with keys, so every run used a disposable Compose project (`acs-a5-qa`) with its own volumes, ports, synthetic credentials, `demo` LLM and `hash` embeddings; the resolved configuration was checked for empty provider keys before start. Images were built fresh and hold migrations `0001`–`0007` (this avoids ENV-01 without touching the developer's images). The developer stack was left running and was not stopped, rebuilt or restarted. Its `api` and `worker` containers bind-mount `services/api`, as before this task (see section 20).

**Baseline run** (before any change, live ingestion): **1,016 passed, 0 failed, 17 skipped** ([log](evidence/AUD-05/baseline/full-suite.log), [JUnit](evidence/AUD-05/baseline/full-suite.xml)); Alembic head `0007`; FORCE RLS clean ([log](evidence/AUD-05/baseline/alembic.log)). This matches A4.1.

## 3. Existing resource-isolation gaps

| Gap | Where (at `db4d352`) |
|---|---|
| PDF, DOCX, TXT and stored HTML parsed inside the long-lived worker | `rag/pipeline.py:179-186`, called at `:371` |
| Live crawl pages parsed inside the worker | `rag/crawler.py:177` |
| No wall, CPU or memory bound on any parse | same |
| No Celery soft or hard time limit | `workers/celery_app.py`, `workers/tasks/ingest.py` |
| No worker memory limit in development, none of CPU or PIDs anywhere | `docker-compose.yml`; `docker-compose.prod.yml` had `mem_limit` only |
| Publish, fail, re-queue and heartbeat not tied to the attempt | `rag/pipeline.py:121-174`, `:249-304`; crawl pages published with no job check at all |
| One organization could occupy every worker slot | `rag/pipeline.py:100-118` |
| Sweeper reset did not re-check the heartbeat | `rag/maintenance.py` |

Already present and preserved: upload size cap, extension/MIME/signature agreement, DOCX entry/size/ratio/path guards with `defusedxml`, PDF page and text caps, SSRF-safe fetcher, atomic publish, compare-and-set claim, bounded retries, one-active-job indexes, stuck-job sweeper.

## 4. Baseline reproduction

Small synthetic inputs only; each probe is bounded on its own ([probe](tools/repro_a5.py), [log](evidence/AUD-05/baseline/repro-parser.log), [memory](evidence/AUD-05/baseline/repro-memory.log), [lifecycle](evidence/AUD-05/baseline/repro-lifecycle.log) with its [test source](evidence/AUD-05/baseline/repro_lifecycle_test.py.txt), [containers](evidence/AUD-05/baseline/container-limits-2.log)).

| Observation | Result on unchanged code |
|---|---|
| A parser slowed to 2 s | ran to completion in the calling process; nothing could interrupt it |
| Celery limits | global and per-task soft/hard limits all `None` |
| 12 / 24 / 48 KB of nested HTML | 0.14 / 0.51 / 1.96 s: roughly quadratic |
| 21 KB PDF with a 20 MB compressed stream | 52.5 MB peak allocation in the worker before any limit applied |
| Superseded attempt resumes after the newer one succeeded | **published a second version** |
| Superseded attempt fails late | **marked the successful document and job failed** |
| Two jobs of one organization | both admitted |
| Worker containers | `Memory=0 NanoCpus=0`, no PID limit |

The first memory probe reported no growth because `ru_maxrss` is inherited across exec here; it is kept, and `tracemalloc` was used instead.

## 5. Parser entry points

| Path | Before | After |
|---|---|---|
| Uploaded PDF, DOCX, TXT | `extract_document` in the worker | `ParserRunner.document` (`pipeline.extract_stored`) |
| Stored web page (reprocess, reindex) | `extract_html` in the worker | `ParserRunner.html` (`pipeline.extract_stored`) |
| Reindex and manual reprocess of files | same as upload | same as upload |
| Live crawl page | `extract_html` in `crawler.crawl` | `ParserRunner.html` (`crawl_job` passes `parse=`; the crawler's default is also isolated) |

Remaining in-process on purpose: upload validation reads the first 4 KiB for signatures (`rag/files.py`), and `robots.txt` goes through the standard library's line parser with a 512 KiB cap (`crawler.load_robots`).

A test breaks the parsers in the parent process only and proves every path above still extracts, so none parses in-process.

## 6. Architecture before and after

```
before   worker process: read original → PARSE → chunk → embed → publish
after    worker process: claim (admission) → read original ─┐
                                                            ▼ pipe: header, bytes
         child (fresh interpreter, limits, empty env):   PARSE
                                                            ▼ pipe: bounded JSON
         worker process: validate result → chunk → embed → publish (fenced)
```

New: `rag/parser_process.py` (child), `rag/parser_runner.py` (supervision and result validation). Pure extraction in `extract.py` and `html_extract.py` is unchanged; a test compares isolated and direct output block for block for PDF, DOCX, TXT and HTML. Fetching, storage, embedding and publication stay in the parent. The AUD-01 query-embedding subprocess is separate and untouched; its asyncio lifecycle and secret-passing contract do not suit a synchronous, secret-free parser.

## 7. Resource limits

| Limit | Value | Enforced by |
|---|---|---|
| Wall clock, from child readiness | 60 s | parent: `SIGKILL` to the process group, reap within 2 s |
| CPU | 30 s | `RLIMIT_CPU` (`SIGXCPU`; hard `SIGKILL` 1 s later) |
| Address space | 512 MiB | `RLIMIT_AS` |
| Core, file size, descriptors | 0, 0, 32 | `RLIMIT_CORE`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE`; `PR_SET_DUMPABLE=0` |
| Input | 25 MiB + 1 KiB (upload) / 5 MiB (fetch) | parent before spawn, existing guards |
| Result | 32 MiB | parent reads at most one byte more, then kills |
| Parent death | — | `PR_SET_PDEATHSIG`, child `SIGALRM` backstop |

The child validates nothing on the parent's behalf: the parent type-checks every field, re-checks the text limit, accepts only known codes and a restricted `detail`, and parses JSON, never pickle. Enforcement tests run through the real child harness; with the limits deliberately disabled, four of them fail ([mutation log](evidence/AUD-05/red/mutation-no-containment.log)).

**Compatibility with supported documents** ([log](evidence/AUD-05/limits/parser-compatibility.log), [boundary](evidence/AUD-05/limits/parser-docx-boundary.log); one run each, QA worker):

| Input | Wall s | CPU s | Peak address space MiB | Result |
|---|---|---|---|---|
| PDF, 500 pages, 1.5 M chars | 1.0 | 0.9 | 45 | parsed |
| DOCX, 4.9 M chars, 6 MiB XML | 0.8 | 0.7 | 77 | parsed |
| DOCX, 4.9 M chars, 23 MiB XML | 2.6 | 2.4 | 333 | parsed |
| TXT, 4.9 M ASCII / CJK / emoji chars | 0.8–1.3 | 0.6–1.1 | 94–177 | parsed |
| TXT, 24 MiB (over the character limit) | 1.8 | — | — | `too_large`, as before |
| HTML, 5 MiB | 3.2 | 3.0 | 60 | parsed |
| DOCX, 39 MiB XML | — | 3.2 | 512 | parsed |
| DOCX, 44 MiB XML | — | — | over | `parse_resource_limit` |

**Compatibility limitation:** a `.docx` whose `document.xml` is larger than about 40 MiB was previously attempted (the archive guard allows 100 MiB) and now fails with `parse_resource_limit`. The budget was not raised for it. The measurements are synthetic; real PDFs with complex fonts or images may cost more.

## 8. Subprocess lifecycle and cleanup

Spawn is `python -E -s -B -m app.rag.parser_process`: fixed arguments, no shell, code directory as working directory, new session, `close_fds`, an empty environment (Windows keeps `SYSTEMROOT` and `WINDIR`). A helper thread does the pipe I/O so the supervising thread always holds its deadline. Whatever ends the wait — result, deadline, oversize, cancellation, or an exception such as the Celery soft limit — the child is killed if running and reaped. No temporary files are created.

When `finally` cannot run (hard time limit, OOM kill, `docker stop`), the kernel's parent-death signal ends the child. Demonstrated: the parent `SIGKILL`ed in a unit test; a real pool process killed (parser gone after 0.05 s); a whole worker killed. Reaping the orphan needs an init: with `init: true` it disappears, without one it stays a zombie ([with](evidence/AUD-05/limits/orphan-with-init.log), [without](evidence/AUD-05/limits/orphan-without-init.log)).

Logs: `parser.finished` carries pid, outcome, exit reason, seconds after readiness, result bytes and the limits. Child stderr is discarded.

## 9. Effective runtime constraints

Both compose files give the worker `mem_limit` and `memswap_limit` 2 GiB, `cpus: 2`, `pids_limit: 128`, `init: true`.

| Where | memory.max | memory.swap.max | cpu.max | pids.max | PID 1 |
|---|---|---|---|---|---|
| Development compose worker ([log](evidence/AUD-05/limits/enforcement-noswap.log)) | 2,147,483,648 | 0 | 200000/100000 | 128 | `docker-init` |
| Production compose worker, `APP_ENV=production`, image from `target: runtime` ([log](evidence/AUD-05/runtime/prod-effective.log)) | 2,147,483,648 | 0 | 200000/100000 | 128 | `docker-init` |

Behaviour, not only configuration ([probe](tools/limit_probe_a5.py), [log](evidence/AUD-05/limits/enforcement-noswap.log)): four busy processes got 6.1 CPU-seconds in about 3 s (throttled in 30 periods); process creation was refused after 123; a 2.25 GiB allocation was killed (`-9`, one OOM kill) while the Celery worker stayed up. The production worker started in production mode (the containment check passed), carried limits 120/180 s and 3240/3300 s, and parsed with containment required. The production-target image parses as UID 10001 without test code ([log](evidence/AUD-05/runtime/parser-in-image.log)).

**Observation, not changed:** the production `beat` service reports `unhealthy` because it inherits the image's HTTP health check; the scheduler itself runs. This is the same at `HEAD` ([log](evidence/AUD-05/runtime/prod-beat-health.log)) and makes `up --wait` fail if it includes `beat`.

**Found while verifying:** `mem_limit` alone let Docker grant another 2 GiB of swap; a 2.25 GiB allocation succeeded ([log](evidence/AUD-05/limits/enforcement-written-pages.log)). `memswap_limit` was added. An even earlier memory probe was invalid because it never wrote its pages ([log](evidence/AUD-05/limits/enforcement.log)).

**Memory under two concurrent large jobs** (two organizations, 4.9 M-character DOCX each, real S3, hash embeddings): both ready on attempt 1 after about 9 s, container peak **0.90 GB (0.84 GiB)**, 10 PIDs, no OOM event ([log](evidence/AUD-05/limits/live-concurrent-2.log)). An estimated worst case of two 512 MiB parsers plus the Celery processes and vectors is near 1.8 GiB: inside 2 GiB, but not by much, and not measured.

## 10. Worker time limits and recovery

Documents: soft 120 s, hard 180 s. Crawls: `20 + pages × (10 + 20 + 60 + 30)` seconds for `CRAWL_MAX_PAGES_LIMIT` pages (24,020 s with 200), capped by `CRAWL_MAX_TASK_SECONDS` to **3300 s hard, 3240 s soft** — under the broker's 3600 s visibility timeout. The budget follows the configured page ceiling, not each source's own `max_pages`. The running worker reports these values ([log](evidence/AUD-05/runtime/worker-reported-limits.log)); only the document limits were driven to expiry.

Containment record for the bounded fixtures — PIDs, exit reasons, effective limits, no child or temporary file left ([log](evidence/AUD-05/limits/containment-record.log)): wall 0.5 s killed 0.505 s after readiness (`SIGKILL`); CPU 1 s ended by `SIGXCPU` after 0.71 s; 256 MiB memory refused the allocation; a 64 KiB result cap stopped reading at 65,537 bytes.

Observed with the installed Celery 5.7 prefork pool: a soft limit raises in the task; a hard limit kills the pool process and **acknowledges** the message; a lost pool process re-queues the message, whose redelivery finds the job `processing` and skips it. In the last two cases only the sweeper recovers the job.

| Case | Behaviour | Retries |
|---|---|---|
| Malformed, encrypted, no text, over a document limit | `failed`, existing codes | none |
| Parser wall, CPU, memory, result limit; malformed result | `failed`: `parse_timeout`, `parse_resource_limit`, `parse_invalid_output` | none; manual reprocess |
| Parser killed from outside, or unable to start | re-queued | bounded by `max_attempts` |
| Storage or database trouble; transient embedding errors | re-queued with backoff (unchanged) | bounded |
| Task soft limit | re-queued, `task_timeout` | bounded |
| Hard limit, worker lost | stays `processing` until swept | bounded by `attempt` |
| Document or source deleted | parser killed within about 1 s; nothing published | none |

**Real-worker results** — disposable worker, own database and Redis databases, test settings: stuck 30 s (default 900), sweep 5 s (default 120), so the bound is 40 s ([log](evidence/AUD-05/green/real-worker-2.log), [data](evidence/AUD-05/green/real-worker-2-data/), [final suite data](evidence/AUD-05/full/backend-final-2-data/)):

| Case | Observed (focused run; the final full suite run in brackets) | Verified state |
|---|---|---|
| Soft limit (3 s) with a hung parser | failed visibly after 2.96 s (3.00 s) | `failed` / `task_timeout`, parser gone, no vectors, worker and permit free |
| Hard limit (4 s), soft limit ignored | recovered 30.7 s after the kill (30.7 s) | `failed` / `internal_error` after the last attempt; next document ready |
| Pool process `SIGKILL` during a reindex | parser gone in 0.05 s; recovered in 34.3 s (34.5 s) | version 1 searchable meanwhile, then `succeeded`, attempt 2, version 2 |
| Whole worker `SIGKILL`, new worker started | recovered in 32.1 s (32.1 s) | `succeeded`, attempt 2, one version, no parser left |
| One message delivered four times | one execution | attempt 1, one version, chunk count matches |

All within the 40 s bound.

With defaults the same bound is about **17 minutes** (900 + 120 + 5 s). The sweeper runs on the same two-slot worker, so two long crawls can delay it further.

## 11. Tenant fairness

At most `INGEST_MAX_ACTIVE_PER_ORG` (1) heavy job per organization, documents and crawls together. The count is taken from `processing` job rows under a per-organization advisory lock in the claim transaction, so it spans processes and has no separate permit to leak; a silent job stops counting after the stuck threshold. A job over the limit is left `queued`, uses no attempt, and is re-published after 2, 4, 8, then 15 s (at most 40 times, then the sweeper). Finishing a job wakes the organization's oldest waiting one.

**Two-slot fixture, real worker** (tenant A's parser hangs until an 8 s test deadline; A also has a second document queued; pool processes warmed first):

| Measure | Target | Focused run | Final full suite |
|---|---|---|---|
| Tenant B queue wait | ≤ 2 s | 0.024 s | 0.026 s |
| Tenant B processing | — | 0.43 s | 0.45 s |
| Tenant B submit to ready | ≤ 5 s | 0.52 s | 0.53 s |
| Tenant A slow job (fails `parse_timeout`) | — | 8.41 s | 8.43 s |
| Tenant A second document ready after the first failed | — | 0.46 s | 0.41 s |

Tenant A's second job stayed `queued` with attempt 0 and no error while the first ran. Tenant B's document stayed `ready` and searchable after A failed.

These are fixture targets, not production SLAs. Costs: a tenant's own uploads wait behind its crawl; the limit does not stop two *different* organizations from filling both slots; and queue order between a tenant's own jobs is not strictly preserved.

## 12. Attempt ownership and fencing

`ingestion_jobs.attempt` increases only on claim and is never reset; manual retry creates a new job row. That makes it a sufficient fencing token, so **no schema change**. Requiring `status = 'processing' AND attempt = mine` now guards: claim, document status change, heartbeat, publication (row locked in the publishing transaction), fail, re-queue, crawl page upsert, page failure, crawl completion, and the cancellation poll. The sweeper re-checks staleness in its update. Lock order is source → document → job.

Two further races were found while re-reading the change, each reproduced before its fix ([red](evidence/AUD-05/red/review-races.log), [green](evidence/AUD-05/green/review-races.log)): the sweeper could fail a document whose *older* job had finished while a newer one was queued; and publishing could deadlock with source deletion (the ordering predates this work).

Not fenced: the object-store write of a crawled page happens after an ownership check but outside any transaction, so a claim lost in that instant could still overwrite the stored raw HTML of one page.

## 13. Document version preservation

Publication is still one transaction (insert version n+1, delete older, mark ready). Tests show a failed reindex (parser limit, embedding, soft limit) and a killed pool process leave version 1 and its chunks searchable; a failed initial ingestion publishes no vectors; recovery publishes exactly one new version.

## 14. Modified files

**New application code:** `services/api/app/rag/parser_process.py`, `app/rag/parser_runner.py`.

**Changed application code:** `app/rag/pipeline.py` (fencing, admission, isolated extraction), `crawl_job.py`, `crawler.py`, `maintenance.py`, `runtime.py`, `errors.py`, `app/core/config.py`, `app/workers/celery_app.py`, `app/workers/tasks/ingest.py`.

**Configuration:** `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `.env.production.example`. The Dockerfile is unchanged.

**Tests:** new `tests/unit/mvp_improvement/test_parser_runner.py`, `test_ingestion_tasks.py`, `tests/integration/api/mvp_improvement/test_ingestion_isolation.py`, `test_ingestion_worker.py`; new support `tests/support/hostile_parser.py`, `file_store.py`, `worker_app.py`, `measure_parser.py`; `tests/support/rag.py` passes the parser into the runtime. No existing test or assertion was changed.

**Documentation and tools:** this report, the progress tracker, `INGESTION.md` (§7, §8), `SECURITY.md`, `DEVELOPMENT.md`, `DEPLOY_CONTABO.md`, `docs/mvp-improvement/tools/*a5*.py`.

Preservation and secret scan: [artifact validation](evidence/AUD-05/artifact-validation.json).

## 15. Migration decision

None. No Alembic revision was added or edited; head stays `0007`. MIG-02 was not touched.

## 16. Regression results

| Check | Result |
|---|---|
| Full backend suite with live ingestion, final tree | **1,116 passed, 0 failed, 17 skipped**, 438 s ([log](evidence/AUD-05/full/backend-final-2.log), [JUnit](evidence/AUD-05/full/backend-final-2.xml), [groups](evidence/AUD-05/full/groups-final.log)) |
| Baseline before changes | 1,016 passed, 0 failed, 17 skipped; no existing test was removed or edited |
| Runtime proxy tests (the 17 skips), image `acs-api:mvp-a5-local` | **17 passed** ([log](evidence/AUD-05/runtime/proxy-tests.log)) |
| `ruff check`, `ruff format --check`, strict `mypy` | pass, 199 files, 197 sources ([log](evidence/AUD-05/static/final-2.log)) |
| Alembic head / current; FORCE RLS | `0007` / `0007`; no unprotected tables ([log](evidence/AUD-05/runtime/alembic-rls.log)) |
| Production-target image build; parser inside it | pass ([build](evidence/AUD-05/runtime/build.log), [parse](evidence/AUD-05/runtime/parser-in-image.log)) |
| Smoke; Playwright (QA web container, port 3010) | all checks passed; **6 passed** ([smoke](evidence/AUD-05/browser/smoke.log), [browser](evidence/AUD-05/browser/playwright.log)) |
| Web and widget unit tests | 220 and 7 passed ([log](evidence/AUD-05/web/unit-tests.log)) |
| `pnpm format:check` | **FAIL**, the same 8 web files as before (FMT-01) ([log](evidence/AUD-05/web/format-check-2.log)) |
| Native Windows: parser and RAG unit tests | 223 passed, 11 Linux-only skips ([log](evidence/AUD-05/windows/native-parser-2.log)) |
| Web lint, type check, production build on the host; CI | **NOT_TESTED** (no web source changed) |

New tests (100): parser runner 51, tasks and limits 15, lifecycle, fencing and admission 28, real worker 6.

| Preservation group (final run) | Passed | Failed |
|---|---|---|
| AUD-01 pool, capacity, lifecycle | 18 | 0 |
| AUD-02 citations | 32 | 0 |
| AUD-03 provider transport | 159 | 0 |
| AUD-04 unit (plus 17 runtime, separately) | 197 | 0 |
| A4.1 admission and migration | 10 | 0 |
| Original audit regressions | 4 | 0 |
| Auth, route permissions, tenant isolation | 89 | 0 |
| Widget; Phase 7 analytics; conversations | 12; 13; 19 | 0 |
| Extraction, files, crawler, SSRF fetcher | 139 | 0 |
| Existing ingestion, deletion, reindex, websites | 95 | 0 |
| Live full-stack ingestion | 1 | 0 |

Full-suite runs after implementation, none removed: 5 failed (test pollution), 1,116 passed, 1 failed (QA environment setting), 1,116 passed. Sections 17 and 19 give the details.

## 17. Performance preservation

Gates unchanged (success P95 ≤ 2,000 ms, rejection P95 ≤ 3,000 ms, success floors, fairness). The series were fixed before running: five repetitions of the strict capacity file without ingestion load, then five with two tenants uploading ~190 KiB documents continuously through the QA worker. The developer stack stayed up (idle) in all runs. Runner: [perf_a5.py](tools/perf_a5.py).

| Series | c100 successful P95 ms (median / min / max) | Failed runs | Ingestion alongside |
|---|---|---|---|
| [No ingestion load](evidence/AUD-05/perf/no-load-5c/summary.json) | 1,611 / 1,533 / 1,636 | 0 of 5 | — |
| [Mixed](evidence/AUD-05/perf/mixed-ingestion-5/summary.json) | 1,588 / 1,558 / 1,652 | 0 of 5 | 44 uploads over 89 s, all `ready` |

The capacity test also ran inside every full suite: success P95 at concurrency 100 was 1,668, 1,649, 1,560 and **1,853 ms** (final). All pass; the spread shows the margin can be as small as about 150 ms.

No unexpected failure in any run. Host CPU before each run was 2–22 %. Two earlier attempts to start the series crashed in my runner before any test ran; their folders hold `ABORTED.txt`.

Limits of this measurement: the host has 32 logical CPUs and the worker is capped at 2, so ingestion could not starve the API of CPU here. It shows ingestion does not reintroduce database starvation on this host; it says nothing about a 4-vCPU production server. PERF-01's thin-margin observation stands.

## 18. Remaining limitations

- **Not a sandbox.** The child has the worker's user id, filesystem view and network. A parser exploit could read files that user can read, including `/proc/<pid>/environ` of the worker (which holds credentials), or open connections. No seccomp, separate user, mount or egress restriction.
- **Linux only.** Native Windows has the parent deadline but no CPU/memory limits, parent-death signal or Celery limits. Deployed environments refuse to run without containment; macOS/Windows production is unsupported.
- Task time limits need the prefork pool.
- DOCX files over about 40 MiB of XML now fail (section 7).
- Recovery from a hard kill takes up to about 17 minutes with defaults, and needs a free worker slot.
- A soft time limit raised inside the S3 client is reported as `storage_error` rather than `task_timeout` (still retried); one arriving in the instant between spawning the child and supervising it is cleaned up by the child's own EOF and alarm, not by the parent.
- Existing deployments: web UI messages for the new codes come from the API's `error_message`; the crawl panel shows the code with spaces.
- Prefork and containment were verified on Docker Desktop (WSL2, cgroup v2, x86-64) only. CI does not run the real-worker or proxy tests (CI-01), and nothing was deployed.

## 19. Failed attempts and fixes

All logs are kept under `evidence/AUD-05/`.

| What failed | Cause | Fix |
|---|---|---|
| First memory and container-limit probes | `ru_maxrss` inherited; template used a missing key | `tracemalloc`; template corrected |
| First green parser run, 1 of 51 | test indexed the wrong block | test |
| First lifecycle run, 9 failures | duplicate upload filename in tests; cached structlog logger hid events (one log-secrecy assertion would have passed vacuously) | tests; the secrecy test now requires events |
| First real-worker run, 6 failures | Celery prefers `CELERY_BROKER_URL`, so the test API published to the QA stack's broker, not the isolated one | fixture pins the variables; only disposable QA services received those messages |
| Worker-loss tests, 2 failures | test killed the process before the parser reached its hang | wait for the fixture's marker ([diagnosis](evidence/AUD-05/red/worker-loss-diagnosis-2.log), [inspection](evidence/AUD-05/red/worker-loss-root-inspect.log)) |
| Soft-limit test, 1 failure | test changed `max_attempts` after the worker could claim | set it before the job is created |
| First static run | lint, format and type errors in new code | corrected ([first](evidence/AUD-05/static/first.log)) |
| Memory limit not enforced | swap allowance | `memswap_limit` |
| Live concurrency run, 403 | wrong `Origin` in the script | script |

| Capacity runner crashed twice | `powershell` not on `PATH`; then a mangled path | full path; aborted series kept and marked |
| First full suite, 5 failures ([log](evidence/AUD-05/full/backend-full.log)) | my tests left jobs active for the cross-tenant sweeper; Alembic's `fileConfig` in my private database disabled existing loggers | cleanup fixture; logger state restored ([reproduction](evidence/AUD-05/red/pollution-minimal.log)) |
| Prettier, 2 Compose files | double space before a comment I added | fixed; back to the 8 known files |
| Final suite, 1 failure ([log](evidence/AUD-05/full/backend-final.log)) | I left the browser run's `CORS_ALLOWED_ORIGINS` in the QA environment; live ingestion got 403 | restored; rerun under a new id |
| Native Windows run, 13 failures | the hostile test fixture imported POSIX-only `resource` at module level; the product parser was unaffected | lazy import ([before](evidence/AUD-05/windows/native-parser.log), [after](evidence/AUD-05/windows/native-parser-2.log)) |

## 20. Rollback and operational notes

- No data or schema change. Reverting the code restores in-process parsing; published chunks and job history are unaffected. Jobs left `queued` by deferral are ordinary queued jobs, and old workers accept the same message arguments (a pending message carrying `deferrals` would be rejected by old code and then re-published by the sweeper).
- Do not roll back by disabling containment in production; stop admitting the problem documents instead.
- Rebuild the API, worker and beat images together. New settings have defaults; see `INGESTION.md` §5.
- Raising `WORKER_CONCURRENCY` requires raising the container limits.
- **Developer machine:** the running developer `api` container hot-reloaded this source and stayed healthy (`/readyz` 200, no traceback, [log](evidence/AUD-05/preflight/developer-stack-after.log)). Its `worker` still runs the old code and has no limits until recreated (`docker compose up -d --build worker beat`). This was not done.

## 21. Requirement results and final decision

| Requirement | Result | Evidence or limit |
|---|---|---|
| A5.1 analysis, entry points, bounded reproduction | PASS | sections 3–5 |
| A5.2 fresh isolated child: bounded input and output, empty environment, no clients, no shell, no pickle, validated result, safe codes | PASS | parser runner tests |
| A5.2 remaining sandbox limits documented | PASS | section 18 |
| A5.3 wall, CPU, address-space, descriptor, input, result limits; kill and reap; orphan cleanup | PASS | real child enforcement; mutation check |
| A5.3 compatibility validated before freezing defaults | PASS, with limitation | DOCX over about 40 MiB XML |
| A5.3 fail closed without containment | PASS (platform detection simulated) | not tried on a real non-Linux deployment |
| A5.4 every extraction path isolated; existing checks preserved | PASS | section 5; unchanged suites |
| A5.5 document soft and hard limits on a real worker | PASS | section 10 |
| A5.5 crawl budget derived, capped, configured | PASS | reported by the running worker |
| A5.5 crawl limit expiry on a real worker | NOT_TESTED | same Celery mechanism as documents |
| A5.5 retry behaviour documented and preserved | PASS | section 10 |
| A5.6 worker memory, CPU, PID limits effective | PASS | both compose files, behaviour probed |
| A5.6 memory measured under concurrent tasks | PASS (typical large documents) | worst case NOT_TESTED |
| A5.7 per-organization admission, bounded rescheduling, no leaked permit, no false failure | PASS | tests and two-slot fixture |
| A5.8 fencing on every transition; version preservation; no stuck jobs; no migration | PASS | one unfenced storage write noted in section 12 |
| A5.9 safe codes, correct classification, manual retry | PASS | |
| A5.10 parser tests 1–18 | PASS | |
| A5.10 lifecycle tests 1–15 | PASS | |
| A5.10 website extraction through a real prefork worker | NOT_TESTED | isolation tested with real children, in-process job |
| A5.10 real worker: soft, hard, restart, child cleanup, reconciliation, version, other tenant | PASS | |
| A5.11 A resource containment (0.5 s budget, ≤ 2.5 s) | PASS | 0.505 s after readiness |
| A5.11 B fairness (start ≤ 2 s, ready ≤ 5 s) | PASS | 0.026 s and 0.53 s |
| A5.11 C recovery within threshold + sweep + 5 s | PASS | 30.7–34.5 s of 40 s |
| A5.11 D existing behaviour preserved | PASS | section 16 |
| A5.12 AUD-01–04 and A4.1 preserved | PASS | |
| A5.13 capacity gates unchanged; mixed workload | PASS (this host) | section 17 |
| A5.14 validation commands | PASS, except | FMT-01 FAIL (pre-existing); CI NOT_TESTED |
| A5.15 report, tracker, evidence, documentation | PASS | |
| Production deployment verification | BLOCKED | no authorized environment |

**AUD-05: PASS (local validation, Linux containers).** Resource containment, worker recovery, durable job lifecycle and tenant fairness are each supported by behaviour observed here. The NOT_TESTED rows and the limitations in section 18 are part of that decision.

Milestone A is **not** complete (AUD-06 and AUD-07 and the open observations remain). **Overall MVP: NOT READY.** AUD-06, AUD-07, MIG-02, FMT-01, CI-01 and Milestones B–J were not started. Nothing was committed, pushed or deployed, and no paid provider call was made.
