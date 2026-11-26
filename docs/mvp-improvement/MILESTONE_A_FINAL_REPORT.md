# Milestone A final report

26 November 2026. Local work only: nothing committed, pushed or deployed; no paid provider call.

## Decisions

| # | Question | Status |
|---|---|---|
| 1 | Original AUD-01 to AUD-07 remediation | **PASS** (local), re-checked ([matrix](MILESTONE_A_CLOSURE_MATRIX.md)) |
| 2 | Local regression validation | **PASS**: 1,209 + 17 backend, 262 frontend unit, 17 browser, 10 of 10 capacity |
| 3 | Formatting and static validation | **PASS** |
| 4 | Migration recovery policy | **DECISION_REQUIRED**: prepared and rehearsed, not approved |
| 5 | Scheduler and maintenance reliability | **PASS** (local); DEVBEAT-CRASH unresolved observation |
| 6 | CI configuration | **PASS** as written and locally exercised, with the gaps listed |
| 7 | Hosted CI execution | **NOT_TESTED** |
| 8 | Public production security | **NOT PASSED**: parser sandbox, ingress/TLS, retention, off-site backup |
| 9 | Real AI quality | **BLOCKED**; offline Recall@5 85% against a 90% target |
| 10 | Overall MVP readiness | **NOT READY** |

**Milestone A local closure: NOT YET CLOSED, pending one decision.** Every local engineering gate
passes and every deferred risk has a disposition in the
[risk register](MILESTONE_A_RISK_REGISTER.md). The brief makes closure depend on the approved
local requirements, and the migration recovery policy (MIG-02) has not been approved. Approving
forward-only (or choosing otherwise and having it validated) is the only thing between this state
and local closure. Closure would not make the product production ready.

## What changed in this final task

* **Formatting (FMT-01).** The eight files differed from the committed versions only by Windows
  line endings in this checkout. Rewritten with LF; they are now byte-identical to `db4d352`, so
  there is no code change to commit. **Correction:** earlier reports implied CI would fail on them;
  the committed files pass Prettier, so a fresh checkout would not have.
* **CI (CI-01).** The old pipeline ran integration tests with only Postgres and Redis, where
  storage, live-ingestion, crawl-worker and proxy tests **skip and still pass**. Replaced with jobs
  that run them on a real stack and fail on any unnamed skip, plus runtime image, restore rehearsal,
  browser journeys and a separate, never-retried capacity workflow. Scripts in `scripts/ci/`.
* **Recovery (AUD05-RECOVERY).** The sweep has its own `maintenance` queue and one-slot worker.
  It now runs while both ingestion slots are busy, runs at `beat` start, and expires if untaken.
* **Scheduler health (OPS-BEAT).** Replaces the inherited HTTP check: `beat` is healthy only while
  the broker accepts its tasks; the consumer only while it answers, consumes its queue and is not
  stuck. Development `beat` and `maintenance` restart on failure.
* **Recovery of data (MIG-02).** `docs/RECOVERY.md`; `deploy/restore.sh`; quiesced backups, run by
  `deploy.sh` before an upgrade; `python -m app.cli verify-data`; a removable guard refusing
  downgrades in staging/production. Migration `0007` was not touched.
* **Found by the rehearsal:** restoring a dump gave the application role deletion rights the source
  had revoked. Fixed.
* **Documented:** what `forget` does not guarantee.

One existing test harness changed: the worker started by `test_ingestion_worker.py` (also used by
the crawl tests) now consumes `maintenance` too, standing for both consumers. No assertion or
threshold changed.

Tests were written first and seen failing for the scheduler health, fingerprint and restore work.
The downgrade guard and queue routing were written before their red run was observed; both were
then shown failing with the behaviour removed.

New: 13 scheduler tests, 3 guard tests, 1 fingerprint test (1,192 → 1,209 backend).

## Audit score

Same 60 items, weights and credit rule as the original audit
([computation](evidence/MILESTONE-A-FINAL/score/implementation_matrix_current.json)).

**Original 80.5 → current 85.75 of 100.** Phases: 8.5/10, 20/20, 10/10, 20/25, 13/20, 14.25/15.

| Item | Was | Now | Why |
|---|---|---|---|
| P1-03 environment safety | partial 0.5 | pass 1 | HTTPS required for providers |
| P1-10 production operations/restore | not tested 0 | partial 0.5 | Restore rehearsed locally only; no alerts or deployment drill |
| P3-10 conversation screen | partial 0.5 | pass 1 | Real data, paginated |
| P5-08 citation correctness/provenance | fail 0 | partial 1 | Provenance fixed; correctness unverified |
| P5-10 concurrent request safety | fail 0 | pass 2 | Local gate; hardware sensitive |
| P6-03 streaming/source display | partial 0.75 | pass 1.5 | Provenance enforced |

Not raised despite related work: P1-07 (hosted CI never ran), P1-09 (no secret manager or history
audit), P6-10 (outage permutations and other browsers untested). Zero credit remains for P4-09,
P4-10, P5-05 and P5-06 (real models).

Limits of the number: the scorer is the engineer who did the work, not an independent auditor;
unchanged passing items are carried on the strength of the current suites and builds, not
re-audited one by one. Status counts: 49 pass, 7 partial, 3 blocked, 1 fail.

**Functional coverage:** sign-up, tenancy, chatbot setup, upload and crawl, retrieval, streaming
chat, widget, inbox and analytics work end to end **with deterministic stand-in providers**. No
real-provider path has been exercised.

**Local engineering readiness:** good for continued development and Milestone B.

## Production release blockers

AUD05-SANDBOX (for untrusted uploads), DEPLOY-01, real-provider validation and RAG quality,
MIG-02 approval, hosted CI, ORG-ORIGINALS, off-site backups and alerting, performance on the
target server.

## Decisions needed from you

1. **MIG-02:** approve forward-only recovery with the downgrade guard? (Recommended.)
2. **Commit and push:** see the [checkpoint plan](MILESTONE_A_GIT_CHECKPOINT_PLAN.md). Pushing a
   branch is what runs CI for the first time. Includes whether evidence goes into Git.
3. **Developer environment refresh (ENV-01):** the procedure is in the risk register; it can
   trigger paid calls for queued jobs.
4. **Milestone B:** needs a provider, a capped key and explicit permission
   ([handoff](MILESTONE_B_HANDOFF.md)).

Work stops here.
