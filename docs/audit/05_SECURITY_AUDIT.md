# Security audit

Decision: **NOT READY**. Confirmed CRITICAL findings: 0; confirmed HIGH availability finding: 1. No cross-tenant leakage observed in the exercised cases. This is not an assurance of universal isolation or an external penetration-test certification.

Dependency advisory checks: pnpm audit and pip-audit reported no known package advisories at execution time. Container/OS CVEs, repository history, deployment IAM, public ingress and secret-manager controls were not fully audited.

## AUD-01 — Concurrent chat exhausts the database pool before admission control

Severity: **HIGH** · Phase: 1,5 · Status: FAIL

Source: `services/api/app/api/deps.py:62`.

Root cause: The request dependency holds an authenticated DB session while find_conversation and generation preparation open additional sessions. The limiter runs after the second lookup. Default pool size 5 plus overflow 5 is exhausted by ten simultaneous request-scoped sessions.

Reproduce: Run AUDIT_CONFIRM_POOL=1 with the staged-performance audit test. Fresh confirmation: 9/10 HTTP 500; QueuePool size 5 overflow 5 timeout 30 seconds. Original 10/50/100 stages all returned HTTP 500.

Impact: Authenticated callers can cause request stalls and HTTP 500s; shared per-process pool pressure can degrade other tenants. No cross-tenant data disclosure was observed.

Evidence: evidence/performance.json; evidence/performance_confirmation.json; evidence/pool_regression.log.

Recommended fix: Release request authentication transactions before slow chat work, avoid nested pool checkouts, and apply admission/backpressure before acquiring scarce DB sessions. Bound pool wait and map overload to controlled 429/503. Re-test cross-tenant fairness.

Suggested regression: Ten concurrent chat requests with default pool must complete or receive documented admission limits, with zero 500s. Include a second tenant health/read request during saturation.

## AUD-02 — Citation eligibility can include a source absent from the rendered prompt

Severity: **MEDIUM** · Phase: 4,5 · Status: FAIL

Source: `services/api/app/rag/retrieval.py:187`.

Root cause: render_context counts escaped characters and may stop before rendering all selected chunks. assemble returns the original selected list; citations_for validates against that list, not rendered sources.

Reproduce: Supply first passage consisting of 2,500 ampersands and a second passage. With a 16,000-byte prompt budget, escaping expands the first passage past render_context's 12,000-character ceiling. Source 2 is absent from the prompt, but Answer [2] still produces its citation.

Impact: An answer marker can receive apparently valid provenance for evidence the model never saw. This is not a cross-tenant leak: affected chunks are still tenant-scoped.

Evidence: evidence/security_regressions.log; services/api/tests/unit/audit/test_prompt_evidence.py:26.

Recommended fix: Return the exact rendered source set/IDs from prompt assembly and validate citation markers against it. Budget escaped content consistently.

Suggested regression: test_citations_must_only_reference_sources_actually_rendered currently fails; cover HTML expansion, metadata overhead and partially omitted sources.

## AUD-03 — Production permits HTTP embedding endpoints

Severity: **MEDIUM** · Phase: 1,4 · Status: FAIL

Source: `services/api/app/core/config.py:265`.

Root cause: Production guards reject hash embeddings but do not require HTTPS for EMBEDDING_BASE_URL. OpenAICompatibleEmbedder accepts http and attaches bearer credentials plus document content.

Reproduce: The audit production-settings test supplies an HTTP embedding base URL and otherwise valid synthetic production settings. No ValidationError is raised.

Impact: If an operator configures HTTP in production, embedding keys and customer text can travel without TLS. Current local configuration contains no real key; no actual credential disclosure was performed or observed.

Evidence: evidence/security_regressions.log; services/api/app/rag/embeddings.py:108.

Recommended fix: Require HTTPS in production/staging as appropriate, reject credentials/query fragments in provider URLs, and disable or strictly validate cross-host redirects.

Suggested regression: test_production_embedding_transport_must_require_https currently fails. Add redirect/certificate validation tests with fixture credentials.

## AUD-04 — Production proxy headers trust every peer

Severity: **MEDIUM** · Phase: 1,2,6 · Status: PARTIALLY_IMPLEMENTED

Source: `services/api/Dockerfile:45`.

Root cause: Runtime uvicorn command uses --forwarded-allow-ips "*".

Reproduce: Static: inspect the runtime CMD. In a disposable deployment, send differing X-Forwarded-For values directly and observe request.client-derived limits.

Impact: If the API is reachable outside a strictly trusted proxy boundary, forged forwarded addresses can evade IP limits and distort audit IP metadata. Token/org limits remain independent barriers. Actual public deployment topology was not tested.

Evidence: services/api/Dockerfile:45; services/api/app/core/request_meta.py:35; docs/PHASE2_SECURITY_REVIEW.md.

Recommended fix: Restrict trusted proxy CIDRs and deny direct ingress; add a deployment assertion and forged-header regression.

Suggested regression: Direct untrusted connections cannot choose the limiter IP; trusted proxy chains resolve the intended client.

## AUD-05 — Document parser lacks hard worker time/resource isolation

Severity: **MEDIUM** · Phase: 4 · Status: PARTIALLY_IMPLEMENTED

Source: `services/api/app/workers/celery_app.py:26`.

Root cause: Format and extraction limits exist, but parsing runs in-process and tasks have no configured soft/hard execution deadlines. Worker containers have no explicit resource limits in Compose.

Reproduce: Inspect task configuration and extract_stored/parse paths; test with a bounded slow parser fixture rather than an unbounded malicious payload.

Impact: A pathological but size-compliant document could monopolize ingestion workers or memory. This is a static hardening gap; an exploit PDF/worker kill was not executed.

Evidence: services/api/app/rag/extract.py:90; services/api/app/workers/tasks/ingest.py:33; docker-compose.yml.

Recommended fix: Add bounded parsing in a constrained process plus worker soft/hard deadlines, memory/CPU limits and safe failure recovery.

Suggested regression: A fixture parser exceeding its wall-clock budget is terminated, marks the job safely and does not starve another tenant.

## AUD-06 — Conversation inbox still displays a placeholder empty state

Severity: **LOW** · Phase: 3,5 · Status: PARTIALLY_IMPLEMENTED

Source: `apps/web/src/components/conversations/conversations-screen.tsx:61`.

Root cause: The screen fetches chatbot options but does not load stored conversations. Filters are disabled and the empty state is unconditional.

Reproduce: Persist a conversation, open Conversations, inspect the component/request behavior; no transcript query is made by this screen.

Impact: Stored public/widget conversations cannot be reviewed from this inbox despite the implemented API and playground history. Advanced Phase 7 analytics are outside this audit; the present placeholder should be labelled accurately.

Evidence: apps/web/src/components/conversations/conversations-screen.tsx:14; baseline conversation persistence tests.

Recommended fix: Within the agreed MVP scope, surface existing conversation data or explicitly communicate the limitation; do not claim the inbox complete.

Suggested regression: After saving a widget conversation, inbox refresh displays it or an explicit unavailable-feature state.

## AUD-07 — Repeated installation has no deduplication or teardown

Severity: **LOW** · Phase: 6 · Status: PARTIALLY_IMPLEMENTED

Source: `apps/widget/src/loader.ts:41`.

Root cause: Every script execution appends another iframe and window message listener. There is no per-key instance registry or cleanup API.

Reproduce: Install the same script/key twice and inspect iframe/listener count; the source contains an unconditional append.

Impact: Accidental duplicate tags or SPA remounts can create overlapping launchers and extra session issuance. Different-key isolation passed; repeated same-key behavior has only static evidence here.

Evidence: apps/widget/src/loader.ts:4,41.

Recommended fix: Define idempotent default initialization with an explicit multi-instance opt-in and remove listeners/frames during teardown.

Suggested regression: Repeated initialization of one key yields the documented instance count and no extra stale listeners.

## Controls that were verified

Server-side membership/permissions, FORCE RLS, tenant/chatbot retrieval filters, opaque expiring sessions, Argon2id passwords, CSRF custom-header/origin checks, upload signatures and bounds, crawler pinned public-IP validation, public capability scope, React/DOM text rendering, and rate/quota checks have passing local tests. See baseline.xml and business_workflow.json for scope. No raw production secrets were printed or copied into these reports.

Live model prompt-injection resistance, semantic faithfulness and unknown-answer correctness are BLOCKED without real-provider access; escaping is not a semantic safety proof.
## Threat coverage and limits

- Broken access control / IDOR / privilege escalation: PASS for the exercised role, manipulated identifier, RLS and widget-capability cases; evidence `baseline.xml` and `business_workflow.json`. No broad external penetration-test claim.
- SQL injection: PARTIALLY_IMPLEMENTED verification. Static retrieval SQL uses fixed query fragments and bound parameters (`rag/retrieval.py:75,79,145,150`); UUID route validation and ORM paths were reviewed. Dedicated dynamic SQL-injection fuzzing was NOT_TESTED. Do not infer universal immunity from parameterized examples.
- XSS: PASS for the hostile widget welcome-text browser case and tested safe rendering; arbitrary rich-content/browser payload coverage is NOT_TESTED. See `apps/web/e2e/widget.spec.ts` and `browser.log`.
- CSRF / session security / CORS: PASS for tested missing custom header, foreign origin, cookie attributes, expiry/revocation and configured preflight cases (`test_auth` entries in `baseline.xml`). Production reverse-proxy trust remains AUD-04.
- SSRF: PASS for tested schemes, private/mixed DNS answers, redirects and pinned public address policy in `test_safe_fetch` / website tests. No production network perimeter test was made.
- Upload security: PASS for exercised format, magic, zip, size and extraction bounds. Hard process resource isolation remains AUD-05. No destructive decompression/resource exhaustion attack was run.
- Storage privacy: tenant-generated object keys and API authorization are verified; local live S3/Celery integration passed. Production bucket/IAM/public-access policy remains NOT_TESTED.
- Sensitive disclosure / hardcoded secrets: settings and server/browser boundaries inspected; auth/audit log hygiene tests PASS. Environment inspection recorded key-presence flags only. Fixture/local placeholders are not reported as leaked production credentials. Repository-history and external secret-manager scans are NOT_TESTED; bounded audit-artifact token checking is not a complete scanner.
- Rate limits / abuse: unit/API quota, token, IP and tenant controls PASS in fixtures; default-pool concurrent admission FAILS AUD-01. Forged proxy metadata is a conditional deployment weakness, not an observed bypass of independent tenant quotas.
- Prompt injection / vector isolation: escaped delimiter and fixture tests PASS structurally; no cross-tenant corpus chunks observed. Real-model obedience/faithfulness/refusal are BLOCKED. Citation eligibility FAILS AUD-02.

