# Phase 6 verification — 2026-11-22

Delivered widget version: **1.0.0**, **4,053 bytes gzipped**; the enforced budget is 10,240 bytes. Deployable bundle and manifest: `services/api/widget_assets/v1/`. Installation/operations guide: [WIDGET_DEPLOYMENT.md](WIDGET_DEPLOYMENT.md).

Executed results:

- Complete backend suite with live ingestion: **582 passed**, no skips or failures (97.57s). Adds eight origin-validation cases and four database/API widget security tests to the existing suites. After the final domain-configuration refinement, its four integration cases and all backend static checks were rerun successfully.
- Frontend/widget tests: **213 web + 7 widget passed**. Existing public-key rotation behavior remains covered.
- Complete final browser suite: **5 passed together** (11.4s). Uses installed Chrome, the real local API/Postgres/Redis/storage/worker stack, a temporary plain HTML server and the production-built Next.js dashboard.
- Workspace ESLint and TypeScript: pass. Prettier: pass. Backend Ruff/formatting and strict mypy: pass. Row-Level Security audit: no unprotected tables.
- Production Next.js build, widget build and production API runtime image build: pass. The runtime image explicitly includes the widget distribution and DNS resolver dependency. No deployment/publishing to an external environment was performed.
- Development database migration **0006** applied; stack smoke checks pass for API/web health, pgvector, migration readiness, Redis, request IDs and a real Celery task. Existing throwaway-database downgrade/upgrade regression also passes with the new migration.
- Visually inspected the generated mobile widget and live dashboard preview screenshots under `apps/web/test-results/` (gitignored).

Browser coverage includes plain HTML and Next.js embedding, streamed replies and stored source citations, hostile welcome text rendered literally without executing scripts, multiple chatbot instances with separate histories, reload resumption, separate site-origin histories, mobile panel sizing, Escape/focus return, copying installation instructions and opening the real live preview. Concurrently loaded instances are selected by public key, since network arrival order is nondeterministic.

Backend coverage includes canonical origin validation, failed/unverified origins, exact CSP framing restrictions, expiring DNS proofs and revocation on failed re-verification, tenant authorization for domain management, resumption bound to a bot/site/expiry, access-token rotation, retention shortening, removal revoking public access, and rejection of public capabilities on admin APIs. Existing Phase 5 rate/concurrency/quota and cross-tenant retrieval tests remain passing.

During verification, repeated browser runs exhausted the development signup limit; only the local signup rate counters were reset for the final combined run. Production/default limits were not increased. The live preview was changed to use the actual isolated frame directly; the installation tab no longer shows an unrelated settings save bar. Earlier unsuccessful runs are not counted as passing evidence.

Limits: the demo provider is a canned offline transport fixture, not a real model-quality evaluation. Actual public DNS ownership checks are tested with mocked resolver responses; production DNS propagation depends on the operator's records. Seven-day DNS proofs require manual renewal. Anonymous retention controls resumption/access expiry and browser persistence, not automatic database deletion. No load or main-thread-time benchmark, wildcard-domain support or automated DNS renewal is claimed. Third-party storage restrictions can prevent reload restoration while in-memory chat continues to work. See deployment guidance for trusted-proxy configuration and privacy operations.

Changed areas: widget source/build distribution, migration/models, domain verification and session services, public frame/asset/bootstrap routes, management APIs, installation/live-preview UI, production API asset packaging, security/browser tests, and documentation. No LLM credentials are embedded in the bundle.
