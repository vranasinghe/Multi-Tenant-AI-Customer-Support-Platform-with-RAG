# Milestone A risk register

26 November 2026. Local evidence only; nothing is deployed. "Dev" = blocks isolated development;
"Public" = blocks a public production release. Planned milestones follow
`docs/MVP_IMPROVEMENT_PLAN.md`; they are proposals until you authorize them.

| ID | Severity | Dev | Public | Disposition | Planned |
|---|---|---|---|---|---|
| AUD05-SANDBOX | High | No | **Yes**, for untrusted uploads | Open, deferred | I1 |
| DEPLOY-01 | High | No | **Yes** | Open, deployment gate | I5 |
| REAL-PROVIDER | High | No | **Yes** | Blocked: needs authorization | B |
| RAG-QUALITY | High | No | **Yes** | Blocked/failed: Recall@5 85% against 90% | B, C, J |
| MIG-02 | High | No | **Yes** | Decision required | now (your decision) |
| CI-HOSTED | Medium | No | **Yes** | Configured, never executed | now (needs a push) |
| ORG-ORIGINALS | Medium | No | **Yes** | Open, deferred | I2 |
| BACKUP-OFFSITE | Medium | No | **Yes** | Open (no PITR, no off-server copy, no alerting) | I2, I3, I5 |
| PERF-01 | Medium | No | **Yes**, until measured on the target | Open, deployment gate | I4 |
| ENV-01 | Medium | Partly | No | Open, procedure below; needs approval | now (your approval) |
| RLS-CHECK | Medium | No | No | Open, new observation | I1 |
| DEVBEAT-CRASH | Low | No | No | Unresolved, not reproduced | observe |
| AUD05-DOCX | Low | No | No | Accepted limitation pending product decision | C1 |
| WIDGET-FORGET | Low | No | No | Documented limitation | H3 |
| WIDGET-ERRORS | Low | No | No | Open, deferred | H4 |
| WIDGET-BROWSERS | Low | No | No | Not tested | H5 |

Closed by this work: FMT-01, CI-01 (configuration; execution is CI-HOSTED), OPS-BEAT,
AUD05-RECOVERY, and the restore privilege defect found during the rehearsal.

## Open risks

### AUD05-SANDBOX — parser is contained, not sandboxed
- **Facts:** every parse runs in a child with CPU, memory, time, descriptor and write limits, no
  secrets in its input. It keeps the worker's user id, filesystem view and network namespace; no
  seccomp (`app/rag/parser_process.py`).
- **Impact:** a code-execution flaw in a PDF/DOCX/HTML parser would run with the worker's database,
  Redis and storage reach.
- **Mitigation:** a separate parser boundary (own user or container, no network, read-only
  filesystem, seccomp). Needs an approved architecture.
- **Accept when:** a hostile child provably cannot open a socket, read the worker's environment or
  files, or signal its parent, in the deployed runtime.
- **Until then:** do not open document upload or crawling to untrusted public users.

### DEPLOY-01 — trusted ingress and TLS unverified
- **Facts:** no peer is trusted by default. With `FORWARDED_ALLOW_IPS` empty every visitor shares
  Caddy's address in IP rate limits. Caddy, TLS and ingress denial have never been exercised.
- **Impact:** one client can exhaust sign-up/login/widget limits for everyone; audit IPs are wrong.
- **Mitigation:** fixed Caddy address (`DEPLOY_CONTABO.md`, "Trusted ingress"), then test.
- **Accept when:** on the real server, limits follow the true client, spoofed headers are ignored,
  the API is unreachable except through Caddy, and TLS and redirects are verified.

### REAL-PROVIDER and RAG-QUALITY
- **Facts:** only `demo` generation and `hash-v1` embeddings have run. Recall@5 on the 100-case
  audit set is the lexical baseline; faithfulness, refusal, citation meaning, injection resistance,
  real latency, cost and provider error behaviour are unknown.
- **Impact:** the core product claim (correct, grounded answers) is unproven.
- **Accept when:** see `MILESTONE_B_HANDOFF.md`.

### MIG-02 — recovery policy not approved
- **Facts:** downgrading below `0007` fails after any conversation deletion, otherwise discards
  Phase 7 data. A forward-only policy, runbook, quiesced backup, verified restore and a downgrade
  guard for staging/production are prepared and rehearsed (`docs/RECOVERY.md`).
- **Decision needed:** approve forward-only (recommended), including the guard.
- **Accept when:** approved, and a restore of production-sized data meets agreed RPO/RTO.

### CI-HOSTED
- **Facts:** workflows are written; their scripts pass locally on Docker Desktop. GitHub has never
  run them; `actionlint` was not available; the browser job uses Playwright's Chromium while local
  runs used Chrome; hosted runners are slower, so timing-bound tests may prove flaky there.
- **Mitigation:** push a branch (needs your authorization) and read the results.
- **Accept when:** every job passes on GitHub without retries or relaxed assertions, and branch
  protection requires them.

### ORG-ORIGINALS — retention of private originals
- **Facts:** soft-deleting a chatbot keeps its originals. Deleting an organization row would
  cascade away its `storage_deletions` outbox, leaving objects nobody tracks. No application path
  deletes organizations today.
- **Impact:** private documents retained indefinitely; deletion promises not met.
- **Mitigation:** a purge that releases every object before rows are removed; a retention period.
- **Accept when:** deleting a chatbot or organization leaves no object under its prefix after the
  declared period, proven against object storage.

### BACKUP-OFFSITE
- **Facts:** nightly local dump and volume copy; restore verified locally on tiny synthetic data.
  `DATABASE.md` states a 14-day PITR target that is not implemented. No off-server copy, failure
  alert or production-sized restore.
- **Impact:** losing the single server can lose everything; up to 24 hours otherwise.
- **Accept when:** encrypted off-server copies, alerting on failure, a timed restore drill.

### PERF-01 — latency depends on the machine
- **Facts:** one event loop saturates; margins on the developer laptop are a few hundred
  milliseconds; a throttled host exceeded the gate (A6.1). Results are in the validation report.
- **Accept when:** the unchanged gate passes repeatedly on hardware sized like the target.

### RLS-CHECK — the protection check is weaker than it sounds
- **Facts:** `check-rls` requires forced RLS and *at least one* policy. Tables with a second policy
  (for example `messages`, which has `owner_read`) still pass with `tenant_isolation` dropped.
  Found while testing `verify-data`, which does notice. No such policy is missing today, and the
  tenant isolation tests cover behaviour.
- **Mitigation:** require `tenant_isolation` (or a named bespoke policy) per table.
- **Accept when:** dropping any expected policy fails the check in CI.

### DEVBEAT-CRASH
- **Facts:** the developer `beat` ran for hours, then raised `TypeError: unhashable type:
  'DbfilenameShelf'` reading its schedule store and stayed down (no restart policy). 4.17 million
  accelerated scheduler ticks on the same Python and Celery did not reproduce it. Cause unknown.
  It is not established that the schedule file was corrupt.
- **Mitigation applied:** development restart policy; health check that reports a scheduler that
  stops publishing.
- **Accept when:** reproduced and fixed, or not seen again over an agreed period with monitoring.

### AUD05-DOCX
`.docx` files with more than about 40 MiB of document XML fail `parse_resource_limit` (512 MiB
parser budget). Decide: state the limit to users, or raise it after measurement.

### WIDGET-FORGET
`destroy({forget: true})` removes the widget after 5 seconds without confirmation, and the resume
entry can then remain; the caller is not told (`WIDGET_DEPLOYMENT.md`). Accept when the API reports
the outcome, or the limitation is accepted by the product owner.

### WIDGET-ERRORS
Some public error `detail` texts are written for operators. Map public errors to visitor wording.

### WIDGET-BROWSERS
Resume storage and journeys ran in Chrome with `localhost` origins only. Test Firefox, Safari and
real cross-site origins before promising resume.

## ENV-01 — developer environment refresh (not executed; needs your approval)

The developer stack runs old images (`migrate` predates `0007`; `worker` runs old code; `beat` has
exited; there is no `maintenance` service yet). Its `.env` holds **real provider keys**, so
restarting workers can make **paid calls** for any queued job.

1. Check pending work, read-only:
   `docker compose exec postgres psql -U platform_owner -d chatbot -c "select status, count(*) from ingestion_jobs group by 1"`.
   Development Redis is not persistent; queued messages are lost on recreate and the sweeper
   re-publishes queued rows.
2. Decide what happens to queued or processing jobs. To refresh without any provider call, keep
   `worker`, `maintenance` and `beat` stopped until the jobs are reviewed. Do not simply switch the
   embedding provider to `hash`: existing vectors came from another model.
3. Back up first (Git Bash):
   `ENV_FILE=.env COMPOSE_FILE=docker-compose.yml COMPOSE_PROJECT_NAME=ai-chatbot-saas BACKUP_DIR=~/acs-dev-backup QUIESCE=1 bash deploy/backup.sh`
4. `docker compose build` (all backend images, so `migrate` includes `0007`).
5. `docker compose up -d postgres redis storage mailpit`, then `docker compose run --rm migrate`.
6. `docker compose up -d api web`; then, only after step 2, `docker compose up -d worker maintenance beat`.
7. Verify: `docker compose ps` all healthy; `docker compose exec api python -m app.cli verify-data`.
8. Do not run `docker compose down -v`: it deletes the developer database and documents.
