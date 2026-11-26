# A5.1 — Ingestion integrity and real-worker crawl validation

Date: 26 November 2026 (Asia/Colombo). Scope: AUD05-STORAGE and AUD05-CRAWL only.

## 1. Decision

**A5.1: PASS for local validation** (Linux containers, disposable stack).

- **AUD05-STORAGE — fixed.** The race was real and reproduced: a superseded crawl attempt could replace the stored HTML of a newer one, and reprocessing would then publish it. Originals are now written under a new key each time and published only by the attempt that owns the job. No database migration.
- **AUD05-CRAWL — validated.** All 14 crawl scenarios ran through a real prefork worker, including both crawl time limits, worker loss and restart. No recovery defect was found.

Final run: **1,148 passed, 0 failed, 17 conditional skips** (the runtime proxy tests, 17/17 separately); lint, format and strict mypy clean; browser 6/6; smoke and FORCE RLS pass; capacity 10/10.

Read with the decision: crawl limits were driven to expiry with shortened budgets, not the 3240/3300 s production values; the capacity margin under continuous crawling was as small as 103 ms; AUD05-RECOVERY, AUD05-SANDBOX, AUD05-DOCX and OPS-BEAT remain open. Nothing was deployed. **The MVP remains NOT READY.**

## 2. Repository baseline

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`, with the uncommitted A1–A5 and earlier user work. Before any edit: SHA-256 inventory of 1,296 files, patch of uncommitted changes, container inventory and developer environment flags without values ([preflight](evidence/A5.1/preflight/preflight.json), [hashes](evidence/A5.1/preflight/before_hashes.json)). No commit, push, reset, clean or history change. One session edited the tree.

**Environment.** A disposable Compose project (`acs-a51-qa`) with its own volumes, ports, PostgreSQL, Redis, RustFS object storage and real prefork worker; synthetic credentials, `demo` LLM, `hash` embeddings, empty provider keys checked in the resolved configuration; images built from the current tree with migrations `0001`–`0007`. The developer stack was not stopped, rebuilt or restarted (section 13).

**Baseline run** before any change, with live ingestion: **1,116 passed, 0 failed, 17 skipped**; Alembic `0007` ([log](evidence/A5.1/baseline/full-suite.log), [JUnit](evidence/A5.1/baseline/full-suite.xml)). It matches the AUD-05 final figures.

The session was interrupted once, just after the baseline. Nothing in the application or tests had changed at that point.

## 3. Confirmed root causes

| Question | Finding at the start of A5.1 |
|---|---|
| How are raw HTML keys generated? | `document_key(org, chatbot, document, 0)`: one fixed key per page document, `…/v0/original` |
| Do attempts write the same object? | Yes. Every attempt and every re-sync of a page overwrote it. A page new to the source got a fresh document id per attempt, so a lost attempt left an unreferenced object |
| When is an object authoritative? | The moment the upload completed: the database already pointed at the key |
| How does the database refer to it? | `documents.storage_key`; size and ETag were updated before indexing |
| What stopped a stale attempt? | A heartbeat check before the upload. The upload itself was outside any transaction |
| Could a stale attempt corrupt the next reprocessing? | **Yes**, reproduced |
| Could cleanup delete a current object? | The purge deleted any queued key without checking whether a document pointed at it |

Reprocessing files uploaded by users was not exposed: each upload has its own key and nothing rewrites it.

## 4. Baseline reproduction (unchanged code)

[First run](evidence/AUD05-STORAGE/red/ownership-on-unchanged-code.log) of the new tests: 13 failed, 7 passed. Writers are paused with events inside the object store, between the ownership check and the write.

| Behaviour | Result on unchanged code | Store |
|---|---|---|
| Attempt A paused before its write; B publishes; A resumes | **A's HTML replaced B's** while B's chunks stayed published | memory and RustFS |
| Worker lost after upload, before commit | the published original was replaced by never-published HTML | memory |
| Re-crawl fails permanently | previous original overwritten and its size changed | memory and RustFS |
| Source deleted during a write, purge runs before the write lands | **the object of a deleted source survived** | memory and RustFS ([log](evidence/AUD05-STORAGE/red/deletion-with-purge-and-overtaken-document.log)) |
| Document job overtaken while indexing (needs `INGEST_MAX_ACTIVE_PER_ORG` > 1 or a silent job) | **published the old content over the newer one** ([probe](evidence/AUD05-STORAGE/red/overtaken-document-job.log), [source](evidence/AUD05-STORAGE/red/probe_overtaken_test.py.txt)) | memory |
| Purge of a queued key that a document points at | deleted it (defence in depth; no normal path produced such a row) | memory |

Several of the other failures are expected on old code because the behaviour did not exist (no record of an upload, no new key). The source-deletion test first passed for the wrong reason — its purge ran only after the late write — and was tightened before any fix.

## 5. Ownership design

**No migration.** The existing `storage_deletions` outbox and `ingestion_jobs.attempt` are enough. New module: `rag/originals.py`.

1. **New key per write**: `orgs/{org}/chatbots/{bot}/documents/{doc}/g-{uuid}/original`. Nothing is overwritten.
2. **Stage** (short fenced transaction): record the key in `storage_deletions` with `created_at` = now + crawl hard time limit + 300 s, the earliest time it may be reclaimed.
3. **Upload** with no transaction open.
4. **Adopt** inside the existing fenced publishing transaction: delete the record, point `documents.storage_key`, size and ETag at the new object, queue the previous one. A document that never published a version adopts at once, so reprocessing keeps working.
5. **Release**: a writer whose upload returned but did not publish makes the record due immediately. A killed writer cannot; the grace period covers it.
6. **Purge**: claims a due record (`attempts + 1`) and commits before deleting the object; keeps referenced and foreign keys. A claimed key can no longer be adopted, so publication fails with a retryable `storage_error` instead of pointing at a deleted object.
7. **Document jobs** publish only if the document still points at the key they read; a missing object that was replaced is retried, not failed.
8. **Deletion** locks the source (or document) before reading its keys.

Row locks on the outbox record serialise publisher and purger. The new paths hold no transaction across object-storage calls. The existing file-upload endpoint still uploads inside its transaction; it was not changed.

`created_at` now means "not reclaimable before" for these rows, and `attempts > 0` "claimed". Reusing them avoided a schema change; it is documented in the model, `DATABASE.md` and `INGESTION.md` §9.

## 6. Modified files

**New:** `app/rag/originals.py`.

**Changed application code:** `app/rag/storage.py` (`generation_key`), `crawl_job.py` (stage, upload, record, release), `pipeline.py` (`StoredOriginal`, adoption and source check at publish, replaced-object retry), `maintenance.py` (`purge_storage`), `app/services/knowledge/service.py` (deletion locks), `app/models/knowledge.py` (docstring).

**Tests:** new `tests/integration/api/mvp_improvement/test_original_ownership.py` (20), `test_crawl_worker.py` (12), `tests/support/gated_store.py`; extended `tests/support/worker_app.py` (real object storage, controlled site fetcher, embedder and store markers) and `hostile_parser.py` (a web page can ask for a hostile mode). No existing test or assertion was changed.

**Documentation and tools:** this report, the tracker, `INGESTION.md` (§2, §3, §8, new §9), `DATABASE.md`, `SECURITY.md`, `tools/capture_a51.py`, `preflight_a51.py`, `perf_a51.py`, `load_crawl_a51.py`, `groups_a51.py`, `verify_a51.py`. Preservation and secret scan: [artifact validation](evidence/A5.1/artifact-validation.json) (no protected file changed, no finding).

## 7. Storage integrity: after

[20 of 20 pass](evidence/AUD05-STORAGE/green/ownership-first.log). Three of the cases (superseded writer, deletion during a write, failed reindex) run against real RustFS as well as in memory.

| Mandatory case | Result |
|---|---|
| Superseded attempt writes after a newer one published (memory, RustFS) | newer original and chunks unchanged; reprocessing uses them; only the authoritative object remains after one purge |
| Superseded attempt fails late | document, job and original unchanged |
| Worker lost during upload / after upload, before commit | published original and chunks unchanged; record protected, reclaimed once due (also with a real `SIGKILL`ed worker, section 8) |
| Duplicate delivery | second delivery skipped; one write, one version |
| Source deleted during a write (memory, RustFS); source or document deleted while publishing | no object remains |
| Purge racing publication | purge first: publication refused, previous version intact, retry succeeds; referenced key: object kept |
| Failed reindex (memory, RustFS) | previous key, bytes, size and chunks kept; reprocessing republishes them |
| Successful re-crawl and reprocessing | reference switches; old object queued and removed |
| Document under the earlier fixed key | moves to a new key at its next publication |
| Document job overtaken while reading or indexing | retried; never publishes the replaced content |
| Cross-tenant | keys stay under their organization; another tenant's record cannot be released |

**Mutation checks** (safeguard removed, tests re-run, files restored byte for byte): without the deletion locks both delete-while-publishing cases leave an object behind; without the claim check the purge-first case fails; without the source comparison the overtaken-while-indexing case fails ([log](evidence/AUD05-STORAGE/red/mutation-safeguards.log), [second](evidence/AUD05-STORAGE/red/mutation-source-compare-2.log)).

## 8. Real-worker crawl results

Disposable Celery prefork worker (`--concurrency=2`, with beat), real queue, private database, Redis databases 13/12, real RustFS. The website is a loopback server. **SSRF protection was not weakened**: only the worker process under test resolves `site.test` to that server; every other host keeps the production resolver and public-address policy, and the application code is unchanged in this respect.

| Scenario | Observed (first crawl run) | Result |
|---|---|---|
| Complete 3-page crawl, production parser command | job 1.3 s; 3 documents `ready`, chunks with 1536-dimensional vectors, searchable, objects stored; 3 parser children | PASS |
| Hung, memory-exhausting, garbled and oversized pages; redirects to metadata, private and another loopback address | 4 page errors (`parse_timeout`, `parse_resource_limit`, `parse_invalid_output`, `too_large`), 3 `blocked`; 2 good pages published; no parser left | PASS |
| Crawl soft limit | failed `task_timeout` 16.0 s after the parser started; parser gone; published version intact | PASS |
| Crawl hard limit (soft limit ignored) | see section 9 | PASS on rerun |
| Whole worker `SIGKILL`ed mid-crawl, new worker started | recovered in 32.7 s (bound 40 s); attempt 2; unchanged page not re-uploaded; no duplicate versions | PASS |
| Worker killed during an upload / after it | recovered in 32.3 / 32.2 s; published original kept meanwhile; abandoned object removed once due | PASS |
| Source deleted mid-crawl | parser cancelled in 0.97 s; no rows or objects left | PASS |
| One crawl delivered four times | one execution, one version per page | PASS |
| Superseded attempt (stalled past the stuck threshold) resumes after attempt 2 | gave up; attempt 2's content, version and original unchanged | PASS |
| Retry exhaustion (2 attempts) | `failed` after 2; no page left `processing`; previous content served | PASS |
| Tenant B while tenant A's crawl hangs | queue wait 0.024 s, ready in 0.54 s; A's own document stayed `queued`, attempt 0, then ran | PASS |

Data: [first run](evidence/AUD05-CRAWL/first/real-worker-data/), [log](evidence/AUD05-CRAWL/first/real-worker.log): 11 passed, 1 failed (section 12). The whole file passes again inside the full suite (section 11).

## 9. Crawl time limits and recovery

The crawl budget is derived from settings, so the tests shrink its inputs instead of adding a test switch. Values reported by the running worker (`inspect registered`):

| | Soft / hard | Inputs |
|---|---|---|
| Production defaults | 3240 / 3300 s | 200 pages, 20 s fetch, 60 s parse, 30 s embedding, capped by `CRAWL_MAX_TASK_SECONDS` |
| Soft-limit test | 16 / 33 s | 1 page, 1 s fetch, 20 s parse, 1 s embedding |
| Hard-limit test | 9 / 19 s | same with 6 s parse |

Stuck threshold 30 s (default 900) and sweep 5 s (default 120): recovery bound 40 s here, about 17 minutes with defaults. The production-length limits themselves were not waited out.

**Hard limit** ([log](evidence/AUD05-CRAWL/green/hard-limit.log), [data](evidence/AUD05-CRAWL/green/hard-limit-data/crawl-hard-limit.json)): killed at 19 s; job `processing` until swept; recovered 15.2 s later as `failed` / `internal_error`; version 1 searchable; the staged upload was protected for 319 s and is gone afterwards.

**Finding.** The installed pool (billiard) sends `SIGTERM` and, 100 ms later, `SIGKILL` on a hard limit, and the child turns `SIGTERM` into `SystemExit`. So `finally` blocks *can* run: here the dying process released its upload, which the sweep removed 126 ms after the kill. That is safe, because release only follows a completed upload, but it is not guaranteed. The `INGESTION.md` §8 statement that a hard limit runs no cleanup was corrected.

## 10. Recovery and operational review

No recovery defect was found in the real-worker scenarios, so nothing in this area was changed.

**New dependencies from this work:** abandoned uploads are removed by the sweep, so they wait while `beat` is down or both slots are busy (delayed, not lost); a killed writer's object can stay up to the grace period (about an hour with defaults) and is not counted against the storage quota; two small transactions are added per changed page.

| Observation | Status | Proposal, for separate authorization |
|---|---|---|
| AUD05-RECOVERY: ~17 min default recovery; sweeper shares the two ingestion slots | OPEN | A dedicated `maintenance` queue consumed by its own one-slot worker (about 256 MiB), routing `ingest.sweep` there; then consider a shorter stuck threshold for documents than for crawls. Accept: with both ingestion slots hung, a killed job is still reset within threshold + sweep |
| AUD05-SANDBOX: shared user, filesystem, network | OPEN | Run the parser as a separate UID with no access to the worker's environment or secrets, in a mount and network namespace (or a separate parser sidecar with no network), plus a seccomp profile. Accept: a hostile fixture cannot read `/proc/<worker>/environ` or open a socket. Empty environment and resource limits are **not** a sandbox |
| AUD05-DOCX: ~40 MiB document XML | OPEN | Product decision: document the limit in the upload UI, or raise the parser budget together with the container limit after measuring |
| OPS-BEAT: inherited HTTP health check | OPEN | Health check on schedule progress, for example a heartbeat key written by `ingest.sweep` with an age limit; verify by stopping beat and observing `unhealthy`. Production `beat` has `restart: unless-stopped`; the development one has no restart policy |
| DEVBEAT-CRASH (new) | OPEN, observation | The developer `beat` container exited at about 07:21 on 26 November with `TypeError` inside Celery's shelve schedule store. It had started before the AUD-05 edits. Not investigated; the health check above would surface a recurrence |
| ORG-ORIGINALS (noted) | OPEN, observation | Chatbot deletion is soft and removes no originals; deleting an organization would cascade outbox rows away with them. Both predate this work |

## 11. Regression results

| Check | Result |
|---|---|
| Full backend suite with live ingestion | **1,148 passed, 0 failed, 17 skipped**, 750 s ([log](evidence/A5.1/full/backend-full.log), [JUnit](evidence/A5.1/full/backend-full.xml), [groups](evidence/A5.1/full/groups.log)) |
| Baseline before changes | 1,116 passed, 0 failed, 17 skipped; the 32 new tests account for the difference; no existing test edited |
| New storage tests; new real-worker crawl tests | 20 passed; 12 passed (inside the full run) |
| Ingestion, website, crawler, SSRF, deletion, reindex and AUD-05 tests, focused | 327 passed ([log](evidence/AUD05-STORAGE/green/existing-ingestion-tests.log)) |
| Runtime proxy tests, image `acs-api:mvp-a51-local` | **17 passed** ([log](evidence/A5.1/runtime/proxy-tests.log)) |
| `ruff check`, `ruff format --check`, strict `mypy` | pass, 203 files formatted, 201 sources ([log](evidence/A5.1/static/second.log)) |
| Runtime Docker build | pass ([log](evidence/A5.1/runtime/build.log)) |
| Alembic head / current; FORCE RLS | `0007` / `0007`; no unprotected tables ([log](evidence/A5.1/runtime/alembic-rls.log)) |
| Smoke; Playwright against a QA web build | all checks passed; **6 passed** ([smoke](evidence/A5.1/browser/smoke.log), [browser](evidence/A5.1/browser/playwright.log)) |
| Web and widget unit tests | 220 and 7 passed ([log](evidence/A5.1/web/unit-tests.log)) |
| `pnpm format:check` | **FAIL**, the same 8 web files as before (FMT-01) ([log](evidence/A5.1/web/format-check.log)) |
| Native Windows: parser and RAG unit tests | 223 passed, 11 Linux-only skips ([log](evidence/A5.1/windows/native-parser.log)) |
| Web lint and type check on the host; CI | **NOT_TESTED** (no web source changed) |

| Preservation group (full run) | Passed | Failed |
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
| AUD-05 parser, tasks, lifecycle, real worker | 51; 15; 28; 6 | 0 |

The same crawl scenarios in the full run: soft limit 16.0 s, hard-limit recovery 15.3 s, restart recovery 32.7 s, upload-loss recovery 32.4 s (bound 40 s), source deletion cancelled the parser in 0.97 s, tenant B waited 0.024 s and was ready in 0.53 s ([data](evidence/A5.1/full/backend-full-data/)). The effective limits and resource limits were not raised and no threshold was changed.

### Capacity

Declared before running ([plan](evidence/A5.1/perf-plan.json)): five repetitions of the unchanged strict capacity file with no load, then five while two tenants continuously re-synced a changing 12-page website through a real prefork worker with the new storage path. Gates: success P95 ≤ 2,000 ms, rejection P95 ≤ 3,000 ms, existing floors and fairness.

| Series | c100 successful P95 ms (median / min / max) | Rejection P95 ms (max) | Successes of 100 | Failed runs |
|---|---|---|---|---|
| [No load](evidence/A5.1/perf/no-load-5/summary.json) | 1,614 / 1,564 / 1,630 | 1,557 | 56–62 | 0 of 5 |
| [Mixed crawl](evidence/A5.1/perf/mixed-crawl-5/summary.json) | 1,762 / 1,666 / **1,897** | 1,707 | 43–53 | 0 of 5 |

Crawl load during the mixed series: 34 crawls and 408 page publications in 98 s, no failed crawl or page, no worker error. The capacity run inside the full suite measured 1,683 ms.

Crawling visibly costs chat headroom: about 150 ms at the median, fewer admitted requests, and a worst margin of 103 ms. Both load and API ran on one 32-CPU development host, and in this series the load worker shared the API container without CPU limits, so it says little about a 4-vCPU server. PERF-01's thin-margin observation stands.

## 12. Failed attempts and fixes

All logs are kept.

| What failed | Cause | Fix |
|---|---|---|
| Source-deletion test passed on unchanged code | its purge ran only after the late write | purge while the writer is paused |
| First overtaken-job probe selected no tests | wrong `-k` expression | rerun under a new id |
| First source-comparison mutation errored at setup; second attempt did not apply the change | the mutation broke the crawl path; then my edit of the mutation script did not match | corrected mutation, run `mutation-source-compare-2`. The run `mutation-source-compare` is invalid and kept |
| Real-worker hard-limit test, 1 of 12 | my test assumed a hard limit runs no cleanup (section 9) | capture the staged key before the kill and require its removal either way |
| First static run | `index_document` over the statement limit; formatting; unused `noqa`; one fixture redefinition warning | helper `_settle_original`; corrected ([first](evidence/A5.1/static/first.log), [second](evidence/A5.1/static/second.log)) |


No full-suite, capacity, proxy, browser or smoke run failed in this checkpoint.

## 13. Rollback and operational notes

- No schema or data change. Existing `v0/original` objects keep working.
- Reverting restores overwriting in place. Old code points documents back at `v0` keys on their next re-crawl; new-key objects they replace are not queued, so they remain unreferenced. Old purge code ignores `created_at`, so any staged record would be purged at once: it only ever names an unpublished object, or one whose publication then fails and retries.
- Deploy API, worker and beat together. A new worker with an old purge is safe for the reason above.
- **Developer machine:** its `api` container bind-mounts the source and reloaded these changes; its `worker` still runs older code with no resource limits until recreated; its `beat` is stopped (section 10).

## 14. Requirement results

| Requirement | Result | Evidence or limit |
|---|---|---|
| S1 root-cause analysis (7 questions) | PASS | section 3 |
| S1 deterministic race reproduction, including reprocessing | PASS | section 4 |
| S1 stale attempts cannot overwrite the authoritative object | PASS | memory and RustFS |
| S1 no transaction held over slow storage work (new paths) | PASS | upload endpoint unchanged |
| S1 failed uploads keep published versions; cleanup cannot delete an authoritative object | PASS | section 7 |
| S1 bounded, recoverable cleanup, including a worker dying mid-way | PASS | grace period plus sweep; needs `beat` and a free slot |
| S1 deletion and reprocessing semantics preserved | PASS | unchanged suites; deletion race fixed |
| S1 no migration | PASS | |
| S1 ten mandatory storage integrity tests | PASS | section 7 |
| S2 successful crawl through the real queue; extraction, chunks, 1536-d vectors; isolated parser | PASS | |
| S2 malformed and resource-limited pages | PASS | |
| S2 crawl soft and hard timeouts demonstrated | PASS | shortened budgets |
| S2 expiry of the production-length 3240/3300 s limits | NOT_TESTED | values reported by the running worker only |
| S2 worker loss, restart, durable recovery within the declared bound | PASS | 32.2–32.7 s of 40 s |
| S2 deletion, duplicate delivery, superseded attempt, retry exhaustion, preserved content | PASS | |
| S2 another tenant proceeds; admission effective; cannot be corrupted | PASS | |
| S2 SSRF and document limits enforced; protection not weakened | PASS | |
| S3 review and proposals | PASS | no code change |
| Preserve AUD-01–05, A4.1, RBAC, RLS, analytics | PASS | section 11 |
| Mandatory validation | PASS, except | FMT-01 FAIL (pre-existing); CI NOT_TESTED |
| Real AWS S3; production deployment | NOT_TESTED / BLOCKED | no authorized environment |

## 15. Remaining limitations

- Not a sandbox (AUD-05 section 18 stands).
- Real-worker results come from Docker Desktop (WSL2, x86-64) with RustFS; no AWS S3, no production host, no CI (CI-01).
- Crawl limits were driven to expiry with shortened budgets only.
- The grace argument relies on the prefork hard time limit; in pools without it (native Windows `solo`, development only) a writer could run longer, in which case publication is refused and retried rather than pointing at a deleted object.
- A server that commits an upload after the client was killed, later than the grace period, would leave an unreferenced object. Not reproduced.

## 16. A5.1 decision

**PASS (local validation).** The authoritative-object regression and the real-worker crawl gates have passing evidence from actual runs. The NOT_TESTED rows and section 15 are part of the decision.

Milestone A is **not** complete (AUD-06, AUD-07 and open observations remain). **Overall MVP: NOT READY.** AUD-06, AUD-07, analytics features, a sandbox redesign, MIG-02, CI-01, FMT-01 and Milestones B–J were not started. Nothing was committed, pushed or deployed, no production database was touched and no paid provider call was made.
