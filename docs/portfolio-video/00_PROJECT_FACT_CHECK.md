# Project fact check

Prepared 26 November 2026. Every claim in this package points to a claim ID (`F-…`) here. If a
claim has no ID, do not say it on camera.

## 1. Evidence levels

| Level | Meaning |
|---|---|
| **CODE** | Read in the current working tree during this preparation |
| **LIVE** | Driven in a browser during this preparation (disposable stack, `demo` LLM, `hash` embeddings) |
| **REPORT** | A project report or stored test artifact. Read, not re-executed |
| **OPEN** | Not verified, not implemented, or needs your confirmation |

What was and was not done while preparing this package:

- The 439 files frozen for the final validation run are **byte-identical** to the working tree
  ([freeze.json](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/freeze.json), hashes compared
  26 November). The reported results therefore describe the current code.
- Test totals were re-read from the stored JUnit files and logs. **No test suite was re-run.**
- The product workflows in section 4 were run live by
  [record.cjs](recording-scripts/record.cjs). No provider key was configured; no paid call was
  possible. The developer containers were not restarted or changed.
- No AI answer quality was evaluated.

## 2. Read this before scripting: conflicts and traps

| # | Finding | Effect on the video |
|---|---|---|
| X1 | The public GitHub repository's `main` branch is the **initial commit only** (`afe3552`). Phase 7 is on a pushed branch. All Milestone A work (the fixes this video describes) is **uncommitted** and not on GitHub | Do not show the GitHub link in either video until the reviewed code is committed, pushed and approved |
| X2 | [README.md](../../README.md) says the platform connects Telegram/WhatsApp. **No such code exists.** Its status line also stops at Phase 5 | Never mention Telegram or WhatsApp as features. Fix the README before sharing the repository |
| X3 | The clips in `output/video/` predate Phase 7 and Milestone A, show placeholder screens, and were recorded with a **Gemini model** ([old storyboard](../../output/video/STORYBOARD.md)) | Do not reuse them. Their answers are not evaluated AI evidence. `output/video/demo-account.txt` holds credentials: never show it |
| X4 | `docs/showcase/Support Platform.png` shows an older UI and badges reading "Scalable" and "Secure" | Do not reuse it |
| X5 | The `demo` provider returns one fixed sentence: "Demo response: this confirms the streaming pipeline works. Check source [1]." ([llm.py:127](../../services/api/app/integrations/llm.py)) | Every chat shot needs the deterministic-demo label. It never answers the question |
| X6 | [SECURITY.md](../SECURITY.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [PRD.md](../PRD.md) are draft **target** designs (billing, channels, MFA, JWT widget sessions). The shipped widget uses opaque hashed tokens | Quote shipped behaviour only |
| X7 | In the retrieval harness, **hybrid did not beat vector-only** ([RAG_EVALUATION.md](../RAG_EVALUATION.md)) | Say hybrid is implemented. Never say it improves accuracy |
| X8 | Found while recording: the Analytics **bar charts render with no visible bars** (bar height resolves to 0; [analytics-dashboard.tsx:25-60](../../apps/web/src/components/analytics/analytics-dashboard.tsx)). Confirmed with a plain-CSS reproduction | Crop to the metric cards. Not fixed here (no application changes were in scope) |
| X9 | Analytics shows an estimated cost and token count even with the offline fixture | Crop both out; they are not real spend |
| X10 | "Grounded rate" means *a reply stored at least one citation* ([analytics-metrics.md](../analytics-metrics.md)), not that the reply is correct | Never present it as accuracy |
| X11 | The Actions tab on GitHub shows green **Dependabot** runs. The project's CI has never run there | Never film the Actions tab |
| X12 | Found while recording: the dashboard checklist item "Add documents or a website" is hard-coded as not done ([overview-dashboard.tsx:79](../../apps/web/src/components/overview/overview-dashboard.tsx)), so it stays unticked after uploads | Crop the "Getting started" panel. Not fixed here |

## 3. Implementation inventory

### 3.1 Implemented

| ID | Feature | Evidence |
|---|---|---|
| F-01 | Sign-up, email verification, login, password reset, sessions | CODE [auth.py](../../services/api/app/api/auth.py); LIVE sign-up and login |
| F-02 | Organizations, invitations, four roles (owner, admin, agent, viewer), audit log API | CODE [policy.py:12-61](../../services/api/app/services/tenancy/policy.py), [orgs.py](../../services/api/app/api/orgs.py) |
| F-03 | Chatbot create, configure, activate; branding | LIVE clips R03, R08 |
| F-04 | Upload PDF, DOCX, TXT (not Markdown or CSV), 25 MiB limit | CODE [files.py:21](../../services/api/app/rag/files.py); LIVE R04 shows "DOCX, PDF, TXT" |
| F-05 | Background processing with Queued → Processing → Ready and passage preview | LIVE R04 |
| F-06 | Website crawling, same host, robots.txt, bounded depth and pages, private addresses refused | CODE [safe_fetch.py](../../services/api/app/rag/safe_fetch.py), [crawler.py](../../services/api/app/rag/crawler.py); LIVE R06 shows the **refusal**. A successful crawl is REPORT only ([A5.1](../mvp-improvement/A5_1_INGESTION_INTEGRITY_REPORT.md) §8) |
| F-07 | Retrieval tester: vector, keyword, hybrid | LIVE R05 (hybrid, `hash-v1`) |
| F-08 | Streaming playground with citations, feedback, and an "Insufficient evidence" fallback | LIVE R07 |
| F-09 | Embeddable widget, verified origins, anonymous resume, ratings, handoff request | LIVE R08, R09, R11 |
| F-10 | Conversation inbox with filters, transcript, sources, outcome actions | LIVE R12 |
| F-11 | Analytics from stored events, CSV export, retention | LIVE R13 (cards); CODE [analytics.py](../../services/api/app/api/analytics.py), [exports.py](../../services/api/app/services/exports.py) |
| F-12 | OpenAI-compatible LLM and embedding adapters | CODE [llm.py](../../services/api/app/integrations/llm.py), [embeddings.py](../../services/api/app/rag/embeddings.py). **Never run against a real provider** in the validated work |

"Handoff" records a request and its status. It is **not** a live agent chat.

### 3.2 Verified local workflows (LIVE, 26 November)

All 15 recorded and passed: sign-in (R01), dashboard (R02), chatbot wizard (R03), upload and
processing (R04), retrieval test (R05), private-address refusal (R06), playground with citation and
fallback (R07), activate and verify origin (R08), widget on a separate-origin site with reload
resume (R09), duplicate install / second instance / destroy (R10), 390 px widget (R11), inbox and
mark resolved (R12), analytics (R13), cross-organization refusal with `404` vs `200` (R14),
dashboard with data (R15).

### 3.3 Technology stack (CODE: manifests and Compose)

| Layer | Used | Version |
|---|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, shared UI package | 16.4.6, 19.3.1, 6.0.3, 4.3.5 |
| Widget | Vanilla TypeScript IIFE loader + iframe, built with Vite | 1.1.0 |
| API | Python, FastAPI, Pydantic, SQLAlchemy, Alembic | 3.13, 0.165.0, 2.14.4, 2.1.9, 1.20.1 |
| Jobs | Celery, Redis | 5.7.0, 8.10.3 |
| Data | PostgreSQL with pgvector | 18, 0.8.7 |
| Objects | S3 API; RustFS locally | 1.0.6 |
| Parsing | pypdf, defusedxml | 7.1.1, 0.7.1 |
| Auth | Argon2id (argon2-cffi), opaque server-side sessions | 25.1.0 |
| Tests | pytest, Vitest, Playwright, Ruff, mypy, ESLint | |

Sources: [pyproject.toml](../../services/api/pyproject.toml),
[web package.json](../../apps/web/package.json), [docker-compose.yml](../../docker-compose.yml).

### 3.4 Application routes

Web ([apps/web/src/app](../../apps/web/src/app)): `/signup`, `/login`, `/verify-email`,
`/forgot-password`, `/reset-password`, `/invite`, `/dashboard`, `/account`, `/orgs/new`,
`/orgs/{org}`, `…/chatbots`, `…/chatbots/new`, `…/chatbots/{bot}`, `…/knowledge`,
`…/conversations`, `…/conversations/{id}`, `…/analytics`, `…/members`, `…/settings`,
`…/billing` (**placeholder**, labelled "Soon").

API ([services/api/app/api](../../services/api/app/api)): `/api/v1/auth/*`, `/me`, `/orgs/{org}/…`
(chatbots, documents, sources, retrieval, conversations, analytics, exports, members, audit logs),
`/public/v1/*` (widget), `/widget/v1/loader.js`, `/healthz`, `/readyz`.

### 3.5 Database (CODE: [migrations](../../services/api/migrations/versions), head `0007`)

22 tables. Identity: `users`, `sessions`, `email_tokens`. Tenancy: `organizations`, `memberships`,
`invitations`, `audit_logs`. Bots: `chatbots`, `chatbot_domains`. Knowledge: `knowledge_sources`,
`documents`, `document_chunks` (`vector(1536)`, HNSW; generated `tsvector`, GIN),
`ingestion_jobs`, `storage_deletions`. Chat: `conversations`, `messages`, `widget_sessions`,
`chat_usage`. Analytics: `conversation_events`, `unanswered_questions`, `analytics_daily`,
`conversation_exports`.

### 3.6 Architecture facts

| ID | Claim | Evidence |
|---|---|---|
| F-20 | **Modular monolith**: one Python codebase and one database, run as several process types. Not microservices | CODE [services/api/app](../../services/api/app); [ARCHITECTURE.md](../ARCHITECTURE.md) §1 |
| F-21 | Processes: `web`, `api`, `worker` (2 slots), `maintenance` (1 slot), `beat` (exactly one), `migrate`; plus PostgreSQL, Redis, object storage, Mailpit (local) | CODE [docker-compose.yml](../../docker-compose.yml) |
| F-22 | Queues: documents→`ingest`, crawls→`crawl`, sweep→`maintenance`, analytics→`default`. `chat_out` and `billing` queues are declared but have **no tasks**: do not draw them as features | CODE [celery_app.py](../../services/api/app/workers/celery_app.py) |
| F-23 | Beat schedule: sweep every 120 s, analytics rollup hourly, retention daily | CODE same |
| F-24 | Chat is an HTTP request answered by an SSE stream from the API. It does **not** go through Celery | CODE [conversations.py](../../services/api/app/services/conversations.py) |
| F-25 | PostgreSQL holds job truth; Redis carries queue messages, rate limits and chat leases | CODE [maintenance.py](../../services/api/app/rag/maintenance.py), [chat_controls.py](../../services/api/app/services/chat_controls.py) |

### 3.7 RAG pipeline

| ID | Claim | Evidence |
|---|---|---|
| F-30 | Extraction for PDF, DOCX, TXT, HTML in a child process | CODE [parser_runner.py:144](../../services/api/app/rag/parser_runner.py) |
| F-31 | Cleaning: Unicode NFKC normalization and zero-width removal; duplicate detection by content hash | CODE [extract.py:70](../../services/api/app/rag/extract.py), [pipeline.py](../../services/api/app/rag/pipeline.py) |
| F-32 | Chunks about 350 tokens with 50 overlap (estimated at 4 characters per token); never cross a heading | CODE [chunking.py](../../services/api/app/rag/chunking.py), [config.py:141-142](../../services/api/app/core/config.py) |
| F-33 | Vector search (pgvector cosine, HNSW) + PostgreSQL full-text OR-query, fused with Reciprocal Rank Fusion, k = 60 | CODE [retrieval.py:31, 95-194](../../services/api/app/rag/retrieval.py) |
| F-34 | Chat applies a minimum vector score (0.15 default, tuned on the hash baseline). Nothing above it → fixed fallback, no LLM call | CODE [config.py:168](../../services/api/app/core/config.py); LIVE R07 |
| F-35 | Candidates are re-authorized from the database immediately before rendering | CODE [retrieval.py:197](../../services/api/app/rag/retrieval.py) |
| F-36 | Only sources actually rendered into the prompt can be cited; unknown markers are removed while streaming | CODE [chat_prompt.py:31, 76](../../services/api/app/services/chat_prompt.py), [retrieval.py:271](../../services/api/app/rag/retrieval.py) |
| F-37 | Offline answer-bearing **Recall@5 = 68/80 = 85%**, target 90% (FAIL). Factual 20/20, paraphrase 12/20, multi-fact 16/20, follow-up 20/20. 100 synthetic cases, 20 fictional documents, `hash-v1` | REPORT [06_RAG_EVALUATION_REPORT.md](../audit/06_RAG_EVALUATION_REPORT.md), [rag_metrics.json](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/suite-data/rag_metrics.json) |
| F-38 | Real-model correctness, faithfulness, refusal, citation meaning, injection resistance: **not measured** | REPORT [MILESTONE_B_HANDOFF.md](../mvp-improvement/MILESTONE_B_HANDOFF.md) |

**Four different things, never merged on screen:** *vector search* finds similar meaning (with a
real model; the hash baseline only matches words); *keyword search* matches terms; *answer-bearing
retrieval* asks whether a returned passage contains the answer; *citation provenance* proves a
cited source was shown to the model; *semantic citation correctness* (does the source support the
sentence?) is **unverified**.

### 3.8 Security boundaries

| ID | Control | Evidence | Limit |
|---|---|---|---|
| F-40 | Role-based access checked on the server for each organization route | CODE [deps.py](../../services/api/app/api/deps.py), [policy.py](../../services/api/app/services/tenancy/policy.py) | |
| F-41 | Opaque session in a `__Host-session` HttpOnly, Secure, SameSite=Lax cookie; only its hash stored | CODE [cookies.py](../../services/api/app/api/cookies.py), REPORT [PHASE2_SECURITY_REVIEW.md](../PHASE2_SECURITY_REVIEW.md) | |
| F-42 | Organization id comes from the URL and is verified per request; non-members get 404 | LIVE R14 | |
| F-43 | PostgreSQL **FORCE ROW LEVEL SECURITY** with a runtime role that cannot bypass it | CODE [rls.py:21](../../services/api/app/core/rls.py) | The CI check requires *a* policy, not each expected policy (RLS-CHECK) |
| F-44 | Widget tokens: random, hashed, 15 minutes, bound to one organization, bot and conversation | REPORT [CHAT_ENGINE.md](../CHAT_ENGINE.md), CODE [config.py:181](../../services/api/app/core/config.py) | Verified origins are defence in depth, not client authentication |
| F-45 | No forwarding-header trust by default; validated allow-list only | CODE [proxy_trust.py:41](../../services/api/app/core/proxy_trust.py), [server.py:19](../../services/api/app/server.py) | Real ingress and TLS untested (DEPLOY-01) |
| F-46 | Provider endpoints must be HTTPS; redirects refused | CODE [provider_urls.py:10](../../services/api/app/core/provider_urls.py) | No real endpoint exercised |
| F-47 | Public widget responses carry an allow-listed shape: no token counts, cost or internal ids | CODE [public_view.py:29-63](../../services/api/app/services/public_view.py) | |
| F-48 | SSRF-safe crawler: public addresses only, connection pinned to the validated IP | CODE [safe_fetch.py](../../services/api/app/rag/safe_fetch.py); LIVE R06 | Network-level egress isolation absent |
| F-49 | **No certification, no external penetration test** | REPORT [05_SECURITY_AUDIT.md](../audit/05_SECURITY_AUDIT.md) | Say so if security is discussed |

## 4. Engineering challenges

### AUD-01 — connection pool starvation (F-50)

- **Problem:** ten concurrent chats → 10 of 10 HTTP 500 after 30 s waits.
- **Root cause:** the request held its authentication DB session while chat preparation opened a
  second one; pool 5 + 5 overflow; admission ran too late.
- **Solution:** release the auth transaction before service work
  ([deps.py:185](../../services/api/app/api/deps.py)); bounded admission with per-organization
  waiters, 3 concurrent chats per organization, 0.9 s window
  ([chat_controls.py:116](../../services/api/app/services/chat_controls.py)); no DB connection held
  during embedding or provider streaming; idempotent lease and turn cleanup
  ([conversations.py:426](../../services/api/app/services/conversations.py)); pool wait 2 s.
- **Validation:** final run at 100 concurrent: **67 served, 33 rejected with a controlled status,
  0 failed**, served P95 1,682 ms ([capacity-100.json](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/suite-data/capacity-100.json)).
  Local fixture provider, one laptop.
- Report: [AUD-01](../mvp-improvement/AUD-01_IMPLEMENTATION_REPORT.md),
  [A6.1](../mvp-improvement/A6_1_PERFORMANCE_STABILIZATION_REPORT.md).
- **Story detail worth telling (F-51):** after the fix the latency gate was still intermittently
  missed; profiling showed one saturated event loop and 10 ms polling
  ([A4.1](../mvp-improvement/A4_1_STABILIZATION_REPORT.md)).

### AUD-02 — citation provenance (F-52)

- **Problem:** a source cut from the prompt by the size budget could still be cited.
- **Root cause:** citations were validated against *selected* chunks, not *rendered* ones; escaping
  expanded the first source.
- **Solution:** one renderer returns an immutable tuple of rendered sources; citations resolve only
  against it; markers are validated across stream chunk boundaries.
- **Validation:** the original failing test passes, with 32 new tests
  ([AUD-02](../mvp-improvement/AUD-02_IMPLEMENTATION_REPORT.md)). Provenance only.

### AUD-05 — document resource containment (F-53)

- **Problem:** parsing ran inside the long-lived worker with no time or memory limit; a stale
  attempt could still publish.
- **Solution:** fresh parser subprocess per document (wall 60 s, CPU 30 s, 512 MiB, 32 MiB
  result), Celery soft/hard limits, attempt fencing, previous published version preserved.
- **Validation:** 100 new tests; real prefork workers killed and restarted
  ([AUD-05](../mvp-improvement/AUD-05_IMPLEMENTATION_REPORT.md)).
- **Mandatory caveat:** **containment, not a security sandbox.** Same user, filesystem and network.
- Cost: a `.docx` with more than about 40 MiB of document XML now fails.

### AUD05-STORAGE — storage consistency (F-54)

Not one of the seven original findings: found during the AUD-05 work.

- **Problem:** a superseded crawl attempt could overwrite the stored HTML of a newer one.
- **Root cause:** one fixed object key per page, written outside any transaction.
- **Solution:** new key per generation; staged in the `storage_deletions` outbox; adopted inside
  the fenced publish transaction; reclaimable if never published
  ([originals.py](../../services/api/app/rag/originals.py)).
- **Validation:** reproduced first (13 of 20 new tests failed), then 20 of 20, three against real
  object storage ([A5.1](../mvp-improvement/A5_1_INGESTION_INTEGRITY_REPORT.md)).

### Widget (F-55)

- Duplicate install kept to one frame; the second instance needs an explicit instance key;
  `destroy` removes frame and listener; resume survives reload
  ([lifecycle.ts:55](../../apps/widget/src/lifecycle.ts)); LIVE R09, R10.
- Interrupted stream stored as `interrupted` with reserved usage kept: REPORT
  ([AUD-07](../mvp-improvement/AUD-07_IMPLEMENTATION_REPORT.md) §8). Not filmable with the demo
  provider (its answer finishes in under a second).
- Loader **5,248 gzip bytes** of a 10,240 budget (F-56):
  [manifest.json](../../services/api/widget_assets/v1/manifest.json),
  [web-2.log](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/web-2.log).
- Chrome and `localhost` origins only.

## 5. Testing results (REPORT, confirmed against artifacts)

| ID | Figure | Artifact |
|---|---|---|
| F-60 | Backend **1,209 passed**, 0 failed, 17 skipped | [backend-full.xml](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/backend-full.xml) |
| F-61 | Runtime proxy **17 passed** (the 17 skipped above, run separately) | [runtime-proxy.xml](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/ci/runtime-proxy.xml) |
| F-62 | Web unit **243**, widget unit **19** | [web-2.log](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/web-2.log) |
| F-63 | Browser journeys **17 of 17** | [browser.log](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/browser.log) |
| F-64 | **Total 1,505** = 1,209 + 17 + 243 + 19 + 17. The 753 Linux unit run is a subset: never add it | arithmetic on F-60…F-63 |
| F-65 | Capacity **10 of 10** declared runs: 5 unloaded, 5 with crawling. Gates: served P95 ≤ 2,000 ms, rejection P95 ≤ 3,000 ms. Tightest margin **25 ms** (1,975 ms) | [unloaded](../mvp-improvement/evidence/MILESTONE-A-FINAL/perf/unloaded-5/summary.json), [mixed](../mvp-improvement/evidence/MILESTONE-A-FINAL/perf/mixed-crawl-5/summary.json) |
| F-66 | Backup and restore rehearsal passed locally; identical counts and hashes; it **found a real defect** (restored database regained `DELETE` grants), fixed | [summary.log](../mvp-improvement/evidence/MILESTONE-A-FINAL/final/ci/restore/summary.log), [validation](../mvp-improvement/MILESTONE_A_VALIDATION_RESULTS.md). Tiny synthetic data |
| F-67 | Deliberately breaking fixes: **10 of 10 breaks detected** by tests (8 in one batch, plus inbox cursor scope and widget de-duplication) | [mutants-all.json](../mvp-improvement/evidence/MILESTONE-A-FINAL/verification/mutants-all.json), [cursor](../mvp-improvement/evidence/MILESTONE-A-FINAL/verification/mutants-AUD-06-cursor-not-scoped.json), [widget](../mvp-improvement/evidence/MILESTONE-A-FINAL/verification/mutant-widget-dedup.log). Same engineer: a second method, not a second reviewer |
| F-68 | Self-audit score **80.5 → 85.75 / 100**, same 60 items and weights. Now 49 pass, 7 partial, 3 blocked, 1 fail | [original](../audit/02_PHASE_IMPLEMENTATION_MATRIX.md), [current](../mvp-improvement/evidence/MILESTONE-A-FINAL/score/implementation_matrix_current.json). Scored by the engineer who did the work |
| F-69 | AUD-01 to AUD-07: **7 of 7 pass locally** | [closure matrix](../mvp-improvement/MILESTONE_A_CLOSURE_MATRIX.md) |
| F-70 | Original audit: 807 original tests passed (582 backend, 213 web, 7 widget, 5 browser); 3 added checks failed; verdict NOT READY | [01_EXECUTIVE_SUMMARY.md](../audit/01_EXECUTIVE_SUMMARY.md) |

Backend test growth (passed): 582 → A1 602 (2 expected open failures) → A2 635 (1) → A3 795 →
*Phase 7 tests added* → A4 1,005 (2) → A4.1 1,016 → A5 1,116 → A5.1 1,148 → A6 1,173 (1) →
A6.1 1,183 → A7 1,192 → final 1,209. Each from the matching report in
[mvp-improvement](../mvp-improvement).

## 6. Current status and limitations

| Area | Status |
|---|---|
| Core engineering | Locally validated |
| Original audit remediation | 7 of 7 pass locally |
| **Formal Milestone A closure** | **Not closed.** Migration recovery policy MIG-02 is `DECISION_REQUIRED` in the newest evidence. Re-check before recording |
| Real AI provider and semantic embeddings | Blocked: never run |
| Semantic RAG quality | Unverified; offline Recall@5 85% vs 90% |
| Hosted CI | Configured ([ci.yml](../../.github/workflows/ci.yml), [performance.yml](../../.github/workflows/performance.yml)), **never executed** |
| Production | **Not ready, not deployed**: parser sandbox, ingress/TLS, retention, off-site backups, alerting, target-hardware performance |
| Overall MVP verdict | **NOT READY** |

Full list: [risk register](../mvp-improvement/MILESTONE_A_RISK_REGISTER.md).

## 7. Planned, not implemented

Real-provider integration and evaluation (Milestone B); reranking, query rewriting, multilingual
evaluation (C); knowledge management upgrades (D); live escalation (E); deeper analytics and
knowledge-gap work (F, G — basic gap grouping exists); UI/UX and widget polish (H); production
security, retention, observability, deployment (I); expanded evaluation and independent audit (J).
Billing, Telegram, WhatsApp, MFA, SSO, OCR: roadmap only.
Source: [MVP_IMPROVEMENT_PLAN.md](../MVP_IMPROVEMENT_PLAN.md), [ROADMAP.md](../ROADMAP.md).

## 8. Never say

"Production-ready" · "enterprise-grade" · "secure sandbox" · "hallucination-free" ·
"accurate AI answers" · "certified" · "CI passing" · "deployed" · "customers" or "users" ·
"microservices" · "scales to …" · "saves businesses …" · "hybrid search improves accuracy" ·
"independently audited".

## 9. Your personal contribution — confirmation needed

What the repository shows:

| Observation | What it does **not** prove |
|---|---|
| Two commits, both authored `vranasinghe`, both dated 25 November 2026 | Development duration or who typed the code. Do not state dates or hours |
| Written briefs and a master prompt with rules and acceptance criteria ([MVP_IMPROVEMENT_PLAN.md](../MVP_IMPROVEMENT_PLAN.md)) | Who wrote them |
| Reports record the user authorizing milestones, stopping parallel sessions, and holding decisions | How much review you did |
| AI coding tools left traces: a `cursor/…` branch, a `codex/…` branch, and Claude Code paths in the final validation commands | The split of work between tools |

Mark each line **YES / NO / REWORD** before recording voice-over:

| ID | Claim | Your answer |
|---|---|---|
| C1 | I planned the project and defined the requirements | |
| C2 | I made the architectural decisions (monolith, RLS, pgvector, Celery) — or approved proposals? | |
| C3 | I wrote the development prompts and briefs | |
| C4 | I reviewed code changes — how closely? | |
| C5 | I debugged problems myself | |
| C6 | I ran tests and validation myself | |
| C7 | I led the performance investigation | |
| C8 | I wrote or edited the technical documentation | |
| C9 | AI tools used: Codex, Claude Code, **Cursor** (also appears in the history) — which, and for what? | |
| C10 | Was this solo work? Is it assessed coursework with rules about AI use? | |

The audits and remediation reports read as AI-agent execution under your authorization. Do not
describe them as work you hand-wrote unless that is true.
