# MASTER DEVELOPMENT PROMPT

## Multi-Tenant AI Customer Support and Knowledge Intelligence Platform — MVP 1.5

### 1. Your role

Act as a senior full-stack software architect, AI/RAG engineer, backend engineer, application security engineer, DevOps engineer, UI/UX specialist, and software quality assurance engineer.

You are working on an existing, partially validated Multi-Tenant RAG SaaS application. Phases 1–6 have already been implemented and audited. Your objective is to improve the existing application into a reliable, secure, professionally designed, deployable, business-ready MVP.

This is an existing-project improvement task, not a greenfield development task. **Do not rebuild the application from scratch.**

---

## 2. Mandatory repository analysis

Before modifying application code, inspect the repository structure, applicable agent instructions, architecture, database schema, migrations, API contracts, frontend components, infrastructure, tests, and audit evidence.

Read all available documents under `docs/`, particularly:

- `PRD.md`
- `ROADMAP.md`
- `ARCHITECTURE.md`
- `DATABASE.md`
- `API_SPEC.md`
- `SECURITY.md`
- `DECISIONS.md`
- `DEVELOPMENT.md`
- `INGESTION.md`
- `CHAT_ENGINE.md`
- `RAG_EVALUATION.md`
- `WIDGET_DEPLOYMENT.md`

Read all twelve original audit reports under `docs/audit/`:

1. `01_EXECUTIVE_SUMMARY.md`
2. `02_PHASE_IMPLEMENTATION_MATRIX.md`
3. `03_ARCHITECTURE_AUDIT.md`
4. `04_FUNCTIONAL_TEST_RESULTS.md`
5. `05_SECURITY_AUDIT.md`
6. `06_RAG_EVALUATION_REPORT.md`
7. `07_PERFORMANCE_REPORT.md`
8. `08_WIDGET_VALIDATION_REPORT.md`
9. `09_MISSING_FEATURES_AND_BUGS.md`
10. `10_PRIORITIZED_FIX_PLAN.md`
11. `11_MVP_READINESS_REPORT.md`
12. `12_TEST_EXECUTION_LOG.md`

Inspect their supporting evidence, test fixtures, logs, JSON results, evaluation datasets, and JUnit reports when available. Treat repository source code and reproducible execution evidence as the authority for current implementation status. Do not assume a feature is complete merely because it appears in documentation.

Identify existing working features, partial implementations, confirmed application defects, placeholders, mock/demo-only functionality, production blockers, missing business functionality, test gaps, unnecessary duplication, and security/performance risks. If a referenced file is missing, record the missing evidence rather than inventing its contents.

## 3. Existing technology stack

Preserve the established technology stack unless a documented technical limitation requires a separately approved change.

| Layer | Existing technology |
|---|---|
| Frontend | Next.js App Router, React, TypeScript, Tailwind CSS, reusable UI components |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data/infrastructure | PostgreSQL, pgvector, Redis, Celery, S3-compatible object storage, local RustFS, Docker/Compose |
| Authentication/security | Server-managed opaque sessions, secure HttpOnly cookies, Argon2id, organization authorization, RBAC, FORCE RLS, CSRF/origin controls |
| Widget | Vanilla TypeScript, versioned IIFE loader, isolated iframe, SSE streaming |
| AI | Existing OpenAI-compatible server-side provider abstraction, existing hybrid retrieval, configurable LLM and embeddings |
| Testing | Pytest, existing frontend test framework, Playwright, Ruff, mypy, TypeScript checks |

Preserve the current layer-first modular monolith architecture. Do not introduce Kubernetes, Kafka, unnecessary microservices, separate vector databases, or additional infrastructure without demonstrated need.

## 4. Known audit baseline

The November 22, 2026 audit reported:

| Metric | Baseline |
|---|---|
| Implementation rubric score | 80.5/100 |
| Original tests | 807 passed |
| Distinct final checks | 811 |
| Final passes / failures | 808 / 3 |
| Runtime-exercised requirements | 51/60 |
| Local answer-bearing Recall@5 | 85% (68/80 answerable cases) |
| Paraphrase retrieval | 60% (12/20) |
| Multi-fact retrieval | 80% (16/20) |
| Measured cross-tenant leaked chunks | 0 |
| Confirmed high-severity findings | 1 |
| Findings | AUD-01 through AUD-07 |
| MVP readiness decision | NOT READY |

Real LLM generation and semantic embedding quality were not validated because the environment used a demo LLM and hash embeddings. These values are historical audit results, not guaranteed current repository state. Reproduce relevant findings before remediation and record any differences. Do not interpret the rubric score as a product completion percentage.

## 5. Non-negotiable development rules

1. Preserve existing verified functionality.
2. Preserve authentication, tenant isolation, RLS, and authorization invariants.
3. Never disable security mechanisms to make tests pass.
4. Never delete, weaken, skip, or mock away a failing regression to hide an application defect.
5. Never fabricate execution results, performance metrics, AI answers, or security evidence.
6. Do not treat canned responses as genuine AI functionality.
7. Do not expose API keys, credentials, internal prompts, or private document contents in browser code or logs.
8. Do not overwrite unrelated user changes.
9. Use small, focused, reviewable implementation changes.
10. Maintain backward-compatible API behavior where practical.
11. Use Alembic migrations for database schema changes.
12. Preserve repository conventions and locked dependency workflows.
13. Add tests for every material behavior change.
14. Avoid unnecessary dependency upgrades.
15. Use disposable local databases and isolated test environments.
16. Do not access production databases, run destructive commands, purchase services, make paid model requests, push commits, or deploy externally without explicit authorization.
17. Never perform deployment or Git history rewriting automatically.
18. Do not claim a requirement is complete when validation remains blocked.
19. Complete only the selected implementation milestone or subtask.
20. Stop at milestone boundaries and report the evidence before starting the next milestone.

---

# MILESTONE A — Audit remediation and system stabilization

Proposed phase: 6.1. Implement AUD-01 through AUD-07 in separately reviewable tasks. Begin with AUD-01 only when instructed.

## A1. Fix AUD-01 — Database connection pool starvation

Investigate `services/api/app/api/deps.py`, authentication dependencies, conversation service, database session factory, request transaction lifecycle, generation preparation, and Redis admission/concurrency controls.

Audit finding: authenticated requests retained a database connection while conversation lookup and generation preparation attempted additional database sessions before admission control. The default pool had five connections plus five overflow connections. The fresh ten-request confirmation returned nine HTTP 500 responses.

Required implementation:

- Use short-lived authentication database transactions.
- Release unnecessary database connections before long-running chat generation.
- Preserve an immutable, validated authorization context; revalidate authorization wherever required to prevent stale permissions or unsafe trust.
- Avoid nested pool checkouts while holding a scarce connection.
- Apply scoped admission controls before expensive chat preparation.
- Preserve tenant-scoped transaction and RLS semantics.
- Ensure sessions close on success, exceptions, cancellation, and disconnect.
- Add bounded connection acquisition waits.
- Return documented HTTP 429 or 503 under controlled overload before streaming begins; use the existing SSE error contract after streaming begins.
- Ensure quota reservations and concurrency leases reconcile correctly.
- Protect availability for other organizations.

Do not solve the underlying issue merely by increasing pool size.

Acceptance criteria:

- Existing failing pool regression passes.
- Repeat concurrency stages 1, 10, 50, and 100.
- Zero unexpected HTTP 500 responses; successful requests genuinely complete and excess requests receive documented admission responses.
- A second tenant remains responsive during saturation.
- No connection, session, quota, or lease leaks.
- Existing authorization and RLS tests continue to pass.

Record before-and-after latency, status distribution, throughput, and relevant database pool observations.

## A2. Fix AUD-02 — Citation provenance

Inspect `services/api/app/rag/retrieval.py`, `services/api/app/services/chat_prompt.py`, citation parsing/validation, prompt assembly and token budgets.

The selected retrieval source set can contain chunks omitted from the rendered prompt.

Required implementation:

- Return the exact rendered evidence set from prompt assembly.
- Keep stable citation identifiers linked to rendered evidence.
- Validate markers only against evidence actually given to the model.
- Account for escaped text, metadata, history, and prompt overhead consistently.
- Reject nonexistent, omitted, or unauthorized source identifiers.
- Preserve valid source information in SSE responses and saved conversations.
- Handle invalid model markers safely and preserve tenant-scoped exposure.

Regression tests: HTML/XML character expansion (including the original ampersand fixture), truncated context, large metadata, long history, empty results, invalid IDs, multiple valid citations, and cross-tenant IDs. Test deterministic source validation and semantic citation correctness separately.

## A3. Fix AUD-03 — Insecure provider transport

Inspect production configuration (`services/api/app/core/config.py`) and provider adapters, including `services/api/app/rag/embeddings.py`.

- Enforce HTTPS for production LLM and embedding endpoints.
- Explicitly separate trusted local development configuration.
- Reject unsafe embedded URL credentials and ambiguous URL components.
- Verify TLS certificates; disable or strictly validate unsafe cross-host redirects.
- Validate provider configuration at startup.
- Prevent secrets and document contents appearing in error logs.
- Document intentionally trusted local provider configurations.

The existing production HTTP embedding regression must pass. Add redirect and certificate-validation tests using fixture credentials.

## A4. Fix AUD-04 — Trusted proxy configuration

Remove unconditional wildcard forwarded IP trust, including the runtime command in `services/api/Dockerfile`.

Implement configurable trusted addresses/CIDRs, safe defaults, forged-header protection, correct client IP resolution behind approved proxies, and documentation enforcing the direct-ingress boundary. Test trusted and untrusted forwarding headers. Do not claim production proxy security until the actual deployment topology is verified.

## A5. Fix AUD-05 — Document parser resource isolation

Inspect PDF/DOCX/website ingestion, Celery settings (`services/api/app/workers/celery_app.py`), parser paths, and worker resource configuration.

Implement hard processing deadlines; soft/hard task timeouts where supported; constrained parser subprocesses or equivalent isolation; platform-appropriate CPU and memory limits; cancellation; temporary-file cleanup; safe failed-job state transitions, retries and recovery.

Preserve upload validation, document size limits, SSRF protection, and extraction rules. Use bounded fixtures, not uncontrolled resource-exhaustion payloads. Demonstrate that a timed-out parser does not starve another tenant.

## A6. Fix AUD-06 — Conversation inbox

Replace the unconditional empty placeholder in `apps/web/src/components/conversations/conversations-screen.tsx` with a minimal functional inbox using persisted data.

Implement conversation listing, chatbot filtering, timestamps, transcript retrieval, loading/empty/error/unauthorized states, and pagination. Preserve tenant-scoped permissions. Advanced conversation management is a later milestone.

## A7. Fix AUD-07 — Widget initialization

Inspect `apps/widget/src/loader.ts` and widget lifecycle.

Implement idempotent initialization per instance key; prevent accidental duplicate launchers/listeners; add iframe teardown and listener cleanup; support SPA mount/unmount and intentionally separate chatbot instances; provide controlled network-error states.

Browser tests: duplicate script tags, same-key repeated installation, different bot keys, navigation/remount, teardown/reinitialization, mobile and desktop.

## Milestone A completion gate

Run original suites and relevant audit regressions. Generate a report for every AUD identifier with source locations, changes, commands, actual results and remaining risks. Do not mark complete while confirmed defects remain unresolved. Deployment-dependent security checks may remain explicitly blocked until deployment validation.

---

# MILESTONE B — Real AI provider integration

Proposed phase: 6.2.

## B1. Real LLM integration

Extend or correct the existing provider abstraction rather than creating a redundant integration system.

Support at least one approved real LLM provider, existing OpenAI-compatible integration where supported, configurable models, server-side credentials, streaming, request timeouts, bounded retries/backoff, cancellation, usage reporting when available, safe error mapping, provider health diagnostics, and clearly identified local demo mode.

Production must not silently fall back to canned responses when the real provider fails. Avoid retrying a partially emitted stream in a way that duplicates output or charges.

## B2. Real semantic embeddings

Implement and validate an approved semantic embedding provider, configurable model identity/version, explicit vector dimensions, database index compatibility, batching, bounded retries, compatible indexing/retrieval embedding spaces, safe reindexing, idempotency and recovery.

Do not assume all embedding models use the currently stored 1536 dimensions. For model or dimension changes, design a safe reindex/migration strategy with rollback. Prevent incompatible embedding models from mixing in the active index.

## B3. Credentials and cost controls

Store credentials in approved environment variables or secret storage. Document configuration using placeholders only. Before paid evaluation, estimate requests/tokens, set request and cost caps, obtain explicit approval, and use fictional or authorized documents.

If no real provider is configured, complete locally testable integration contracts and mark live evaluation BLOCKED. Never invent successful provider calls.

## Milestone B completion gate

Demonstrate a genuinely generated answer from approved knowledge through the configured real model, with valid citations and persisted history. Reindex the evaluation corpus using real embeddings. Record model versions, configuration, timing, usage, and limitations. A blocked live run is not a release pass.

---

# MILESTONE C — Advanced RAG intelligence

Proposed phase: 6.3. Improve the existing hybrid pipeline without replacing proven components unnecessarily. Establish a real-provider baseline before optimization.

## C1. Document processing and chunking

Implement or improve heading/paragraph-aware chunking, configurable size/overlap, document version metadata, extractable page numbers, source URLs/sections, normalized text, duplicate detection, and source traceability. Exclude deleted or superseded content from active retrieval.

## C2. Hybrid retrieval optimization

Preserve PostgreSQL full-text search, pgvector semantic search, tenant/chatbot filters, and current-document-version restrictions.

Evaluate semantic and keyword top-k, Reciprocal Rank Fusion or justified alternative, candidate diversity, score calibration, metadata filters, retrieval thresholds, and duplicate suppression. Never substitute globally retrieved unscoped candidates for tenant-filtered retrieval.

## C3. Reranking

Add optional reranking only when evaluation demonstrates benefit. Retrieve a bounded candidate set, rerank authorized candidates only, select final evidence within context budgets, measure latency/cost, support disabling, retain baseline fallback, and compare before/after metrics.

## C4. History-aware query rewriting

Implement standalone rewriting for follow-ups. Example: after “What is your return policy?”, the question “What about damaged items?” should resolve the relevant subject without inventing facts.

Use bounded history, preserve intent, restrict history to the authorized conversation, prevent cross-conversation contamination, handle ambiguity, and fall back safely on rewriting failure.

## C5. Grounded answer generation

The assistant should answer using supported evidence, cite relevant rendered evidence, refuse unsupported facts, identify conflicting information, ask for clarification when needed, avoid inventing company policies/prices/products/contact details, treat documents as untrusted data rather than higher-priority instructions, and respect approved tone/response settings.

Prompt escaping alone is not semantic prompt-injection protection. Keep grounding mandatory unless a separately approved product policy changes it.

## C6. Multilingual evaluation

Support English and evaluate Sinhala/mixed-language questions as a proposed differentiator. Test English questions with English documents; Sinhala questions with English and Sinhala documents; mixed Sinhala-English questions; and cross-language follow-ups. Select models by observed quality and report category results separately.

## C7. Advanced RAG playground

Extend the authorized playground with original/rewritten queries, retrieval strategy, retrieved chunk IDs/excerpts, retrieval/rerank scores, rendered evidence, model/embedding versions, citation validation, retrieval latency, time to first token, generation latency, token consumption, estimated cost and expected/actual answer comparison.

Do not expose credentials, unrestricted internal prompts, or other tenants' content. Restrict diagnostics to appropriate workspace roles.

## Milestone C completion gate

Evaluate major optimizations independently. Report measurable improvements against the unchanged baseline. Do not retain expensive or complex optimizations without demonstrated value.

---

# MILESTONE D — Professional knowledge base management

Proposed phase: 7.

Improve existing document management with:

1. PDF/DOCX ingestion.
2. Website ingestion.
3. TXT/Markdown support where appropriate.
4. Structured CSV ingestion with defined parsing limits.
5. Manual FAQ creation and editing.
6. Document preview and extracted-text preview.
7. Processing status/progress.
8. Failed-job retry.
9. Search and filtering.
10. Reindexing and version history.
11. Knowledge source health indicators.
12. Configurable website synchronization.
13. Safe source deletion.

The FAQ editor must support CRUD. FAQs must enter the same authorized retrieval lifecycle as other sources.

Website synchronization must respect existing URL/SSRF safeguards, use bounded crawling, detect changes, avoid unnecessary re-embedding, support cancellation, apply tenant quotas, and respect crawl policies.

Use actual backend job states (pending, processing, ready, failed, updating or existing equivalents). Do not display fabricated progress.

**Completion gate:** End-to-end source/FAQ CRUD, indexing, synchronization, retries, and deletion are validated; deleted knowledge is no longer retrieved.

---

# MILESTONE E — Conversation management and escalation

Proposed phase: 8.

Extend the minimal inbox with real conversation lists/transcripts, search/date/chatbot filters, open/resolved/needs-attention status, customer feedback, poor-answer flagging, source inspection, authorized export, and support request management.

Implement basic human-support escalation, not a full live-agent chat platform. Support customer-provided contact method, contact reason, conversation reference, consent where necessary, ticket creation/status, and dashboard notification.

Apply data minimization, retention, tenant authorization, and audit logging. Do not claim delivery to a human agent unless the delivery mechanism actually succeeded.

**Completion gate:** Real persisted conversations and tickets are visible only to authorized tenant users; status, filters, feedback and escalation work end to end.

---

# MILESTONE F — Analytics and usage intelligence

Proposed phase: 9.

Build analytics backed by real persisted events and usage records. Required metrics:

- Total conversations, messages, active chatbots, and activity trends.
- Positive/negative feedback, insufficient-evidence responses, unanswered-question trends, and escalations.
- Response latency, time to first token, input/output tokens, and estimated provider cost.
- Ingestion statistics and rate-limited/failed requests.

Implement date and chatbot filtering, organization-level aggregation, empty states, consistent time zones, server-side pagination/aggregation, and indexes justified by query patterns.

Define metrics before aggregation. Never use hardcoded chart data in the operational dashboard. Do not equate completed conversations with successful customer resolution. Label cost estimates. Add configurable tenant limits and warnings while preserving existing quotas/rate controls.

**Completion gate:** Metrics reconcile with persisted records, filters work, and cross-tenant analytics access is blocked.

---

# MILESTONE G — Knowledge gap detection

Proposed phase: 10.

When an answer cannot be supported:

1. Record an appropriate unanswered-question event.
2. Classify the potential reason.
3. Group similar questions where feasible.
4. Show frequency and affected chatbot.
5. Surface the gap in the organization dashboard.
6. Allow authorized review.
7. Allow creation/update of an FAQ.
8. Index approved knowledge.
9. Retest representative questions.
10. Mark the gap resolved only when appropriate.

Distinguish missing knowledge, poor retrieval, ambiguous queries, provider failures, policy refusals, and invalid/inaccessible source data.

Never automatically convert generated answers into trusted knowledge. Require human approval before publishing suggested FAQs. Keep events/content tenant-scoped and apply privacy/retention rules to recorded questions.

**Completion gate:** An unsupported question can be resolved through a human-approved knowledge update, then demonstrably retrieves the new evidence.

---

# MILESTONE H — Professional UI/UX and chatbot customization

Proposed phase: 11. Preserve the existing design system and improve reusable components. Do not redesign functioning pages without justified UX benefit.

## H1. Dashboard

Improve navigation/workspace switching, information hierarchy, cards, tables, filters, skeletons, empty/error states, notifications, responsive layout, accessible forms, keyboard interactions, typography/spacing and destructive-action confirmations.

## H2. Onboarding

Provide a coherent flow:

Workspace creation → Chatbot creation → Knowledge upload → Knowledge readiness → AI testing → Appearance customization → Website installation → Performance monitoring.

Track actual backend progress. Never mark indexing or deployment complete prematurely.

## H3. Widget customization

Provide validated settings for chatbot name, logo/avatar, brand colors, welcome message, suggested questions, launcher position, language preferences, tone/response length, support contact details and desktop/mobile preview. Validate user-controlled styling/text; preserve safe rendering, tenant isolation, iframe isolation and verified origins.

## H4. Widget reliability

Improve disconnection feedback, duplicate-safe retries, cancellation, session expiry, source rendering, anonymous resume, responsive layout, focus management, rate-limit messages and provider-unavailable states. Keep a lightweight versioned loader; measure gzip size against the existing 4,053-byte audit baseline before adding substantial dependencies.

## H5. Accessibility

Evaluate relevant WCAG 2.2 AA criteria via automated and manual tests: keyboard navigation, visible focus, labels, contrast, screen-reader behavior, reduced motion where applicable, responsive layouts. Do not claim full compliance without sufficient evidence.

**Completion gate:** Verified onboarding and external-widget browser journeys with real backend data; no regressions in existing browser tests.

---

# MILESTONE I — Production readiness, security, and performance

Proposed phase: 12.

## I1. Production security

Review and validate authentication/session lifecycle, membership/RBAC, RLS, IDOR/privilege escalation, CSRF/CORS, XSS, SQL injection, SSRF, upload validation, parser limits, provider HTTPS, proxy trust, secret management, repository-history secret scanning, private object-storage IAM, widget capabilities, rate limits, cost/quota abuse, model prompt injection, and cross-tenant leakage.

Add targeted tests and preserve existing security regressions. Separate confirmed runtime defects, static concerns and unverified deployment risks.

## I2. Data retention and privacy

Implement or document configurable conversation retention, anonymous session expiry, approved physical deletion of expired records, tenant-scoped deletion jobs, document/vector deletion, authorized exports, safe log retention, and recovery/deletion behavior. Access expiry is not physical deletion.

## I3. Observability

Add or improve structured logs, request correlation IDs, API latency/error metrics, database pool metrics, queue depth, worker failures, ingestion duration, provider latency, token/cost usage, readiness and health checks. Avoid logging full conversations, prompts, source documents or credentials by default.

## I4. Performance and resilience

Run controlled tests at concurrency 1, 10, 50, and 100. Include sustained moderate load, multi-tenant fairness, dashboard and public-widget traffic, ingestion during chat, pool pressure, Redis failure/recovery, provider timeouts, client cancellation, and worker restarts.

Record successful/failed request latency separately where possible, P50/P95, throughput, status codes, timeouts, resource usage and TTFT. Controlled admission responses are acceptable when capacity is exceeded, provided admitted requests succeed and other tenants remain responsive. Do not claim production capacity from a short fixture benchmark.

## I5. Deployment readiness

Prepare and validate production Docker builds, environment configuration, secure reverse proxy/HTTPS, migrations, separate API and worker processes, database persistence, private storage, Redis, backup/restore, alerts, graceful shutdown, rollback and CI/CD.

Perform a real backup/restore drill in an authorized non-production environment. Do not deploy externally without explicit approval.

**Completion gate:** No unresolved release blockers; verified operational/security boundaries, controlled overload, and documented recovery evidence. Mark deployment-dependent checks BLOCKED if the environment is unavailable.

---

# MILESTONE J — AI evaluation and final independent audit

Proposed phase: 13. Run relevant evaluation throughout earlier milestones as well; do not wait until the final audit to discover core AI failures.

## J1. Existing benchmark

Preserve the 100-question dataset: 20 factual, 20 paraphrase, 20 multi-fact, 20 follow-up, and 20 unknown/adversarial cases. Preserve the 20-document fictional corpus for regression comparison. Run the same baseline protocol. Do not silently alter expected answers or denominators to increase scores.

The original answer-bearing Recall@5 is a case hit rate across 80 answerable questions (at least one top-five chunk from the expected document containing all configured phrases); unknown cases are excluded. The original follow-up probe explicitly expanded the query with the prior question; do not misrepresent this as proof of the production rewrite path. Report original-comparable metrics and genuine end-to-end follow-up metrics separately.

## J2. Expanded evaluation

Create at least 200 additional reviewable cases covering unseen paraphrases, multi-document questions, ambiguity, contradictions, updated/deleted knowledge, long context, English/Sinhala/mixed questions, conversation follow-ups, unsupported questions, prompt injection, and cross-tenant access attempts.

Keep development and held-out test sets separate from the original benchmark. Freeze held-out cases before final assessment. Do not tune on held-out cases and call them independent evidence.

## J3. Quality targets

| Metric | Proposed acceptance gate |
|---|---|
| Answer-bearing Recall@5 | ≥90% |
| Answer correctness | ≥90% |
| Faithfulness | ≥95% |
| Semantic citation accuracy | ≥95% |
| Appropriate insufficient-evidence refusal | ≥95% |
| Cross-tenant leaked content | 0 observed in measured cases |
| Invalid deterministic citation resolution | 0 |
| Unexpected HTTP 500 responses | 0 in tested workloads |
| Unresolved confirmed critical/high findings | 0 |
| Original and added regression tests | All pass |

These are acceptance goals, not guaranteed outcomes. Define correctness (fully correct answerable responses), faithfulness (supported factual claims), semantic citation accuracy (correctly supported citations), and refusal (appropriate responses to unknown/adversarial cases) before evaluation. Define partial-credit rules, empty denominators and judge disagreement handling. Use human-reviewed labels/evidence. Document automated judge limitations and review disagreements. Do not fabricate scores when credentials or reviewer access are unavailable. Justify any target revision before evaluation rather than fitting it to results.

## J4. End-to-end business workflow

Validate with real application components:

1. Register a workspace owner and verify identity.
2. Create an organization and chatbot.
3. Upload knowledge documents and create FAQs.
4. Wait for genuine indexing completion; verify persisted chunks/vectors.
5. Ask factual/paraphrased questions; validate grounded answers and citations.
6. Customize the chatbot and install it on an external test website.
7. Send customer questions; verify streaming and persistence.
8. Review conversations through the inbox and provide feedback.
9. Trigger an unsupported question; review its knowledge gap.
10. Approve a new FAQ and verify subsequent retrieval.
11. Inspect analytics/usage, and create a support escalation.
12. Create a second organization and verify cross-tenant isolation.
13. Delete a source and verify it is no longer retrieved.
14. Verify documented retention and cleanup.

Prefer one coherent journey where practical. Clearly identify separate fixtures and blocked stages; do not describe layered evidence as a single fully verified workflow.

---

# 6. Required test execution

Inspect and reproduce commands in `docs/audit/12_TEST_EXECUTION_LOG.md`. Verify each recipe against the current repository before execution. Use the existing local development setup and disposable test state. Avoid concurrent test runs against shared Redis test state.

Baseline commands:

```powershell
docker compose exec -T -e LIVE_INGESTION=1 api pytest -q
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy
corepack pnpm -r --if-present lint
corepack pnpm -r --if-present typecheck
corepack pnpm -r --if-present test
corepack pnpm -r --if-present build
corepack pnpm --filter @acs/web exec playwright test
node scripts/smoke.mjs
docker compose exec -T api python -m app.cli check-rls
```

Focused audit commands:

```powershell
docker compose exec -T api pytest tests/unit/audit -q --tb=short
docker compose exec -T -e AUDIT_CONFIRM_POOL=1 api pytest tests/integration/api/audit/test_implementation_audit.py::test_staged_isolated_performance -q --tb=short
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit api pytest tests/integration/api/audit/test_implementation_audit.py::test_business_workflow_and_100_case_evaluation -q --tb=short
```

Run all 1/10/50/100 stages by omitting `AUDIT_CONFIRM_POOL`. Ensure the no-500 acceptance assertion is applied to the full workload, not merely the short confirmation. Run targeted checks during implementation and broader regressions at milestone boundaries. Preserve original audit artifacts before reruns overwrite outputs. Copy relevant container artifacts to a separate improvement evidence directory.

Preserve actual command output, exit codes, elapsed times, test counts and relevant artifacts. A passing evaluation harness is not proof that its measured quality targets passed. Keep distinct test counts separate from rerun counts and evaluation cases.

Use reporting vocabulary: PASS, FAIL, PARTIALLY_IMPLEMENTED, BLOCKED, NOT_TESTED, NOT_IMPLEMENTED, NOT_APPLICABLE.

# 7. Documentation and evidence deliverables

Preserve original audit reports and evidence. Create a separate improvement directory (adapt to existing repository conventions):

```text
docs/mvp-improvement/
├── 00_CURRENT_STATE.md
├── 01_IMPLEMENTATION_PLAN.md
├── 02_PROGRESS_TRACKER.md
├── 03_AUDIT_REMEDIATION.md
├── 04_AI_PROVIDER_VALIDATION.md
├── 05_RAG_EVALUATION.md
├── 06_SECURITY_VALIDATION.md
├── 07_PERFORMANCE_VALIDATION.md
├── 08_FEATURE_VALIDATION.md
├── 09_DEPLOYMENT_READINESS.md
├── 10_FINAL_MVP_READINESS.md
├── CHANGELOG.md
└── evidence/
```

For every milestone document objective/scope, existing findings, modified files, decisions, migrations, security implications, new tests, actual commands/results, limitations, remaining issues, rollback and next milestone. Update product and architecture documentation only when changes are verified.

# 8. Final portfolio deliverables

After functional validation, prepare a professional README, accurate description, architecture/database/RAG diagrams, technology stack documentation, installation instructions, environment template, API/widget guides, fictional business knowledge base, demonstration workflow, actual screenshots, before/after audit comparison, performance benchmarks, AI evaluation results, and security controls/limitations.

Use actual evidence. Do not describe the product as enterprise-grade or production-ready without adequate verification.

# 9. Definition of done

The improved MVP may receive a release-ready decision only when:

- Confirmed critical/high-risk release blockers are resolved.
- All mandatory regression tests pass.
- Real LLM and semantic embedding workflows are verified.
- Approved RAG quality thresholds are met.
- Tenant isolation is validated across expanded tests.
- Deterministic citation provenance and semantic accuracy are validated.
- Concurrent overload is handled safely.
- Knowledge management works end to end.
- The widget works on external test websites.
- The conversation inbox displays real data.
- Analytics use persisted records.
- Knowledge gap resolution works using approved content.
- Production security boundaries and operational procedures are verified.
- Deployment and rollback procedures are validated.

A numeric audit score alone cannot waive a failed release gate. Keep this status explicit if full production validation remains blocked.

# 10. Immediate execution instruction

**For the first execution, DO NOT implement every milestone.** Begin with read-only repository analysis.

Produce:

1. Current implementation inventory.
2. Verification of the twelve audit reports against current source and available evidence.
3. Confirmation of existing and unresolved AUD findings.
4. Dependency and architecture assessment.
5. Prioritized improvement plan.
6. Proposed files/modules to modify for Milestone A.
7. Proposed regression tests.
8. Risks, assumptions and required permissions.
9. Milestone dependency map.
10. Exact acceptance criteria.

Save planning documents only when explicitly authorized. Do not modify application code during initial planning. Stop after presenting the implementation plan.

After approval, execute only the selected milestone or subtask. Follow this cycle:

**Analyze → Plan → Reproduce failure → Implement → Test → Review → Refactor → Revalidate → Document.**

Do not automatically begin the next milestone. The goal is not merely more features, but a trustworthy, maintainable, measurable, professionally demonstrated Multi-Tenant AI Customer Support and Knowledge Intelligence Platform.
