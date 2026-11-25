# Phase 5 — Executed verification

Date: 2026-11-22 (Asia/Colombo). Scope: conversation engine, restricted public chat transport and dashboard Test chat tab. No paid model requests were made.

## Results

- **Backend: 570 passed, zero failures, zero skips** in the final complete run (`docker compose exec -T -e LIVE_INGESTION=1 api pytest -q`; 91.13s). Includes existing authentication, tenancy/RLS, ingestion, retrieval evaluation and live-service tests, plus Phase 5 provider and conversation regressions.
- **Web: 213 passed** across 24 test files. Includes new stream parser and playground component tests.
- **Widget: 7 passed**. Total frontend/widget: **220 passed**.
- **Browser E2E: 4 passed** against the real local stack in installed Chrome (10.9s). The new chat demo uses the explicit offline provider; existing chatbot creation and knowledge tests also pass.
- **Formatting/lint/type checks: pass.** Workspace Prettier, ESLint and TypeScript; backend Ruff, Ruff formatting and strict mypy (154 source files).
- **Builds: pass.** Recursive workspace production builds; Next.js production Docker image rebuilt and used for E2E. Existing widget loader remains 474 bytes gzipped, below its 10KB limit; its installable chat UI is still a later phase.
- **Database: migration 0005 at head.** Upgrade/downgrade/upgrade tested in the fixture's disposable `chatbot_test_*` database. The development database was upgraded only, retaining existing data. RLS audit returns `{"status":"ok","unprotected_tables":[]}`.
- **Stack smoke: pass.** API health, Postgres/pgvector, migration head, Redis, web-to-API readiness, request IDs, dashboard rendering and a real Celery worker roundtrip.
- **Visual inspection:** inspected generated desktop and 390px mobile screenshots. The mobile regression test confirms no document-level horizontal overflow. Screenshot artifacts are local and gitignored under `apps/web/test-results/chat-desktop.png` and `chat-mobile.png`.

## What the new tests prove

- Relevant indexed knowledge reaches generation through real tenant-scoped retrieval. Stored citation metadata maps to retrieved documents; unknown citation numbers are stripped, including across chunk boundaries.
- Empty knowledge and an unrelated question return a deterministic fallback without invoking generation.
- Complete prior user/assistant pairs are reused; callers can lower the context window to zero. Prompt budgeting drops old pairs before source passages.
- Hostile document markup is escaped in user-role evidence and does not enter the system message. Direct attempts to supply a `role` or alternate conversation ID are rejected.
- An outsider cannot read or advance another tenant's conversation. Matching knowledge in another tenant cannot enter generation prompts or citations. The existing retrieval evaluation's tenant isolation suite also continues to pass.
- Provider usage is persisted, used for estimated cost, and reconciled with the durable reservation. Organization rate limits and quotas are enforced before generation; concurrent reservations cannot spend the same remaining allowance.
- Conversation serialization and organization concurrency caps prevent overlapping turns. Leases release after normal completion, failure and interruption.
- Generator cancellation and actual ASGI disconnects close the upstream stream and persist partial replies as `interrupted`. Both ASGI 2.3 and 2.4 paths and socket send errors are covered.
- Timeouts/provider failures produce failure events and persisted failure states, retaining uncertain usage conservatively. Compatible-provider tests cover bounded pre-output retries, malformed/truncated streams and usage parsing.
- Public capabilities only access their own conversation. Tampering, expiration, bot key rotation, attempts to use a bearer token on dashboard routes, and session lifetime message limits are checked.
- Oversized requests, control characters and invalid Unicode fail validation before storage/generation.
- The browser parser handles UTF-8/CRLF network splits and refuses a truncated stream as success. Source links reject unsafe protocols and credentials. The component tests cover live updates, history restoration, source display, usage display, feedback, Stop and viewer restrictions.

## Reproduce

Follow [CHAT_ENGINE.md](CHAT_ENGINE.md) for local demo steps and real-provider configuration. The complete executed command equivalents are:

```powershell
docker compose exec -T -e LIVE_INGESTION=1 api pytest -q
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy
docker compose exec -T api python -m app.cli check-rls
docker compose exec -T api alembic current
corepack pnpm format:check
corepack pnpm -r --if-present lint
corepack pnpm -r --if-present typecheck
corepack pnpm -r --if-present test
corepack pnpm -r --if-present build
corepack pnpm --filter @acs/web exec playwright test
node scripts/smoke.mjs
```

The local global pnpm is older than the project's required version, and native uv is also older. Root scripts that invoke those globals were blocked by their version guards. Verification therefore used the pinned pnpm through direct recursive Corepack commands and the pinned Python/uv environment inside Docker. The Docker dependency build accepted `uv sync --locked` after moving the already-pinned httpx2 transport into runtime dependencies. No global tool upgrades were required.

The rollback test initially exposed Alembic's logging configuration disabling existing application loggers when invoked in the pytest process. The test now runs the migration CLI in subprocesses, matching operational execution; the final full suite, including access-log tests, passes.

## Material limits

- No real-provider response quality, pricing accuracy, production latency or load claim is established by these results. The offline demo is a canned transport fixture; provider tests use mock HTTP transport. Real embeddings, model behavior and relevance thresholds require evaluation with customer knowledge.
- Prompt delimiting and text-only rendering reduce injection/output risk but cannot prove an external model always follows instructions. There are no tools or external actions available to generation.
- Public sessions require an authenticated, verified member with channel-management permission to issue them. Anonymous domain-verified issuance and the installable widget UI remain Phase 6.
- Static monthly operational caps precede billing/plan entitlements. Ambiguous provider usage and process crashes retain reservations conservatively. Operator reconciliation, retention/purge workflows, provider failover/circuit breakers and the earlier trusted-proxy deployment finding remain documented work.
- The expanded repository roadmap also proposes a larger generation-quality dataset, debug traces and other acceptance criteria beyond the user's Phase 5 brief. Those are explicitly not claimed complete.

## Main changes

- Backend: conversation schemas/models, migration `0005`, dashboard/public chat routers, compatible/demo/disabled provider adapters, prompt assembly/citation validation, orchestration, Redis leases, durable quota reservations, bounded request bodies and server-only settings.
- Frontend: streamed fetch client and SSE parser, typed conversation endpoints, integrated Test chat tab, source/usage display, feedback, Stop, restored history and responsive layout.
- Configuration: compose/environment options and runtime transport dependency/lock metadata.
- Tests/docs: provider/unit/integration/concurrency/disconnect/migration regressions, browser demonstration, current API/database/security/roadmap notes and the reproducible chat guide.
