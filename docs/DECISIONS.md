# Architecture Decisions & Open Questions

| Field | Value |
|---|---|
| Status | Draft v0.1 — for review |
| Date | 2026-11-21 |
| Related | All docs in `docs/` reference these IDs |

**How to read this file**
- **Part A, Open questions (Q-xx):** decisions that need **your confirmation**. Each has a recommended default that the other docs already assume. If you answer differently, the "affects" column lists the docs and phases to revise.
- **Part B, ADRs (ADR-xxx):** architecture decisions with context, alternatives and consequences. Status is either **Accepted** (architect's call, low regret, reversible) or **Proposed** (tied to an open question).
- New decisions are appended as new ADRs; superseded ones are marked, never deleted.
- IDs are stable references, not priorities. Gaps in numbering are intentional (merged or withdrawn questions).

---

## Part A — Open questions requiring confirmation

Ordered by how soon they block work.

| ID | Question | Recommended default | Why it matters | Needed by | Affects |
|---|---|---|---|---|---|
| **Q-02** | Hosting target? | Managed containers (AWS ECS Fargate + RDS Postgres + ElastiCache + S3, or Render/Fly for speed) — **no Kubernetes** | IaC, CI deploy, KMS, network egress controls | P0 | ADR-022, ARCH §16, SECURITY §16 |
| **Q-04** | Production region / data residency at launch? | One region; **EU (Frankfurt/Ireland)** if early customers are EU-based, otherwise US-East. Second region post-MVP | GDPR transfers, LLM provider region, latency | P0 | ADR-031, SECURITY §13 |
| **Q-07** | Which LLM/embedding provider(s) and models at launch? Who pays? | OpenAI (or Azure OpenAI for EU residency) via the OpenAI-compatible abstraction; Platform-managed keys; chat: a small fast model default + a larger model on higher tiers; embeddings: `text-embedding-3-small` (1536-d) | Cost model, latency, residency, dimension lock-in | P2 | ADR-012, ADR-015, PRD §10 |
| **Q-05** | Stripe Billing, or a Merchant of Record (Paddle / Lemon Squeezy)? | **Stripe** (Checkout + Portal + Stripe Tax) if the company can handle sales-tax/VAT registration; MoR if you want tax/compliance outsourced | Tax liability, payout countries, webhook model | P3 (account setup) | ADR-017 |
| **Q-08** | Pricing & plan limits? | PRD §10 placeholders; finalize after measuring COGS per message in P3 | Quotas, margins, model tiering | P6 | ADR-018, PRD §10 |
| **Q-03** | Target market: self-serve SMB only, or enterprise requirements at launch (SSO, audit export, DPA negotiation)? | SMB self-serve first (A1) | Moves SSO/SCIM/residency into MVP if enterprise | P1 | PRD §6, ROADMAP |
| **Q-06** | Is Telegram required for GA, or can it follow? | P1: in MVP if on schedule; GA does not block on it | Schedule | P6 | ROADMAP P8 |
| **Q-09** | WhatsApp approach: platform Meta app + Embedded Signup (needs Meta Tech Provider approval), or customer-managed apps (manual connect)? | Target Embedded Signup; **start Meta verification in P5**; manual connect as interim | Onboarding friction, lead time | P5 | ADR-020 |
| **Q-10** | Transactional email provider? | Postmark or Amazon SES (or Resend) behind an interface | Deliverability, DPA | P1 | ARCH §4 `notifications` |
| **Q-12** | Domain layout for cookies: `app.` + `api.` subdomains with CORS, or the web app proxying `/api` on one host? | Subdomains + CORS with credentials (cleaner separation, the widget needs `api.` anyway) | Cookie & CSRF setup | P1 | ADR-004, ARCH §7.1 |
| **Q-13** | Does playground usage consume message credits? | **Yes**, it costs us LLM money; show it clearly in the UI | Fairness vs cost | P6 | ADR-018 |
| **Q-14** | Data handling for expired/unpaid orgs? | Read-only access; purge 90 days after expiry with warnings at 30/7/1 days | Storage cost vs win-back | P6 | ARCH §12.3, DATABASE §6 |
| **Q-17** | Embedding storage: `vector` (float32) or `halfvec` (float16)? | `halfvec(1536)`: half the storage and index memory, with negligible recall loss for this use case. Validate in P3 eval | Storage cost / scaling headroom | P2 | ADR-012, DATABASE §3.4 |
| **Q-15** | Answer caching for repeated questions? | Not in MVP (freshness and correctness first); revisit with FAQ-heavy tenants | Cost vs staleness | post | ARCH §14 |
| **Q-16** | Is hybrid retrieval (FTS + vector) required for MVP? | P1: build vector first, add FTS+RRF in P3 if eval shows gains (likely for product names, SKUs and codes) | Answer quality on exact terms | P3 | ADR-014 |
| **Q-18** | File formats at launch? | P0: PDF (text), DOCX, TXT, MD. P1: HTML, CSV. Post: OCR, PPTX, XLSX | Parser surface & effort | P2 | ADR-026 |
| **Q-19** | Malware scanning of uploads at launch? | Not in MVP (files are never served to other parties); ClamAV post-MVP | Customer security questionnaires | P2 | SECURITY §10 |
| **Q-20** | Signup with an already-registered email: anti-enumeration (same response + email) or explicit "account exists" error? | Anti-enumeration | Security vs UX friction | P1 | API_SPEC §3.1 |
| **Q-21** | Product analytics vendor (PostHog/Amplitude/none)? | PostHog (self-hostable, EU cloud) for dashboard users only, **never inside the widget** | Privacy, subprocessor list | P1 | SECURITY §13 |
| **Q-22** | Is human handoff / live inbox needed in MVP? | No — fallback message with contact details; handoff in v1.2 | Large scope (realtime inbox, agent role) | P0 (scope) | PRD §4, ROADMAP §4 |
| **Q-23** | Does the trial require a credit card? | No card; 14 days; trial limits | Conversion vs abuse | P6 | PRD §10 |
| **Q-24** | Branding removal as a paid feature? | Yes, Growth and above | Pricing | P5 | PRD §10 |
| **Q-25** | Dashboard UI languages at launch? | English only; bots answer in the user's language | i18n scaffolding in P0 if not | P0 | PRD A2 |
| **Q-01** | Product name & domains? | TBD — placeholders `example.com`, `PlatformBot` used throughout | Cookies, email domain, widget host, bot user-agent | P0 | All |

---

## Part B — Architecture Decision Records

### ADR-001 — Modular monolith with process types
**Status:** Accepted
**Context:** Small team (A7), one product, shared data model, mandated FastAPI + Celery.
**Decision:** One Python codebase (`apps/api`) deployed as `api`, `worker` (per-queue deployments allowed) and `beat`. Modules have explicit `public.py` facades; boundaries are enforced by `import-linter` in CI. Next.js and the widget are separate deployables because they are separate runtimes, not separate services.
**Alternatives:** Microservices (ingestion, RAG, billing, channels) were rejected: distributed transactions, duplicated tenancy/auth, more infra and on-call load with no current scaling need. Serverless functions were rejected because of long-running ingestion, SSE streaming and cold starts.
**Consequences:** Simple deploys and local transactions. Extraction stays possible later because modules communicate via facades and job payloads. Boundary discipline must be enforced by tooling, not goodwill.

### ADR-002 — Shared database, shared schema, row-level isolation (RLS)
**Status:** Accepted
**Context:** Thousands of small tenants; strong isolation required; small ops team.
**Decision:** `org_id` on every tenant table; Postgres RLS with `FORCE`; transaction-local GUCs; composite FKs `(org_id, parent_id)`; app-layer scoped repositories; narrow `SECURITY DEFINER` resolver functions for pre-tenant lookups; separate `BYPASSRLS` role only for system jobs. Org context comes from the URL path.
**Alternatives:** Schema-per-tenant (migration fan-out, connection/catalog bloat beyond ~1k tenants) and database-per-tenant (cost and ops) were rejected. App-only filtering was rejected because one missed `WHERE` leaks data.
**Consequences:** Cheap tenants and single migrations. Risks are RLS mistakes (mitigated by CI policy checks and a tenancy suite) and noisy neighbours (mitigated by per-org caps, and partitioning later). Enterprise "dedicated DB" would be a future deployment mode, not a code fork.

### ADR-003 — pgvector inside the primary PostgreSQL
**Status:** Accepted
**Context:** MVP scale is ≤ ~10M chunks; vectors must respect tenant isolation and be consistent with document state.
**Decision:** Store embeddings in `document_chunks` with an HNSW index; Postgres FTS for the lexical leg; one backup and one transaction boundary.
**Alternatives:** Dedicated vector DB (Qdrant, Pinecone, Weaviate) was rejected for MVP: second consistency domain, separate tenant isolation model, extra vendor/DPA. It stays a scaling option behind the `rag` retriever interface.
**Consequences:** Deleting a document removes its vectors atomically, and RLS applies to vectors. Filtered-ANN recall needs care (iterative scans, exact scan for small bots, partitioning plan — DATABASE §5). Vector load shares resources with OLTP, so monitor and plan read replicas/partitioning.

### ADR-004 — Opaque server-side sessions for the dashboard
**Status:** Accepted (cookie domain layout depends on Q-12)
**Context:** First-party web app; need instant revocation and minimal token handling in the browser.
**Decision:** 256-bit random session token in a `__Host-` HttpOnly cookie, SHA-256 stored in `sessions`, cached in Redis 60 s. CSRF via SameSite=Lax + custom header + Origin check. JWTs are used only for the stateless, short-lived widget sessions.
**Alternatives:** JWT access + refresh tokens were rejected because they are harder to revoke, more client complexity, and their statelessness doesn't help a first-party app. A third-party auth SaaS (Auth0/Clerk) was rejected as an extra vendor and per-MAU cost. That remains reasonable if SSO is needed fast (revisit with Q-03).
**Consequences:** One cache/DB lookup per request (cheap); straightforward "log out everywhere".

### ADR-005 — Fixed roles: owner, admin, agent, viewer
**Status:** Accepted
**Decision:** Static role → permission mapping in code (SECURITY §4); endpoint-level permission dependencies; domain-tested policies (last owner, admin cannot touch owners).
**Alternatives:** Custom roles/ABAC were rejected for MVP (UI and testing cost). Per-chatbot permissions are post-MVP.
**Consequences:** Simple and auditable.
**Amendment (Phase 1):** the content-editing tier is named **`agent`** (it was `editor` in the first draft) with exactly the permission set the draft gave to editors. This follows the Phase 1 brief. A separate live-chat handoff role, if one is ever needed (v1.2), still requires a new ADR and a matrix update.

### ADR-006 — UUIDv7 identifiers; separate public widget key
**Status:** Accepted
**Decision:** UUIDv7 PKs generated in the app (native `uuidv7()` once on PG 18). Widget uses a separate rotatable `pk_live_…` random key, never the chatbot UUID.
**Alternatives:** Serial ints (enumerable, leak volume), UUIDv4 (poor index locality), prefixed string ids like `bot_…` (nice DX, but non-native type; may add display prefixes in API later).
**Consequences:** Ids are sortable by time and safe to expose. The public key can be rotated without changing references.

### ADR-007 — Celery + Redis for background work; Postgres holds job truth
**Status:** Accepted
**Decision:** Celery 5 with Redis broker, `acks_late`, idempotent tasks, named queues (`ingest`, `crawl`, `chat_out`, `default`, `billing`), enqueue after commit, DB-backed job state, beat sweepers for lost/stuck jobs. Transactional outbox only for loss-intolerant events without a natural sweeper.
**Alternatives:** RQ, arq, Dramatiq (lighter, async-friendly) were rejected because Celery was mandated and has mature routing and beat. Postgres-only queues (e.g. procrastinate) are viable but were not chosen given the mandate.
**Consequences:** The API is async and the workers are sync (two session factories). Reliability doesn't depend on Redis durability.

### ADR-008 — Server-Sent Events for streaming
**Status:** Accepted
**Decision:** SSE over `POST` (parsed with `fetch` streams) for playground and widget answers; Telegram/WhatsApp use non-streaming generation.
**Alternatives:** WebSockets were rejected: bidirectional channel not needed, harder through proxies/LBs, more state. Long polling was rejected as worse UX.
**Consequences:** Plain HTTP infrastructure. Proxies must not buffer (`X-Accel-Buffering: no`, LB idle timeout ≥ 60 s).

### ADR-009 — Iframe-based widget with per-bot `frame-ancestors`
**Status:** Accepted
**Decision:** A tiny loader injects an iframe from `widget.example.com`. The iframe shell is served by the API with a CSP `frame-ancestors` listing the chatbot's verified domains. The widget authenticates with a short-lived JWT.
**Alternatives:** Shadow-DOM in the host page was rejected: tokens exposed to host scripts, CSS leakage, no browser-enforced domain gate. Pure script on host + CORS allowlist was rejected because CORS alone doesn't stop non-browser abuse and leaks tokens to host JS.
**Consequences:** Strong isolation and a browser-enforced embedding restriction. There is a cross-frame resize/open protocol to maintain. Storage is partitioned per top-level site (privacy-positive).

### ADR-010 — Domain verification via meta tag or DNS TXT
**Status:** Accepted
**Decision:** A domain must be verified before it is allowed in `frame-ancestors`/session issuance. Meta tag (default, easy) or DNS TXT (required for wildcards). Weekly re-verification with a grace period. Localhost only in time-boxed test mode.
**Alternatives:** Unverified allowlist (anyone could claim a competitor's domain → minor risk but confusing analytics and abuse); file-based `/.well-known` (similar to meta, may add later).
**Consequences:** Small onboarding step; prevents casual embedding on unrelated sites.

### ADR-011 — Knowledge scoped to a chatbot (no shared knowledge bases in MVP)
**Status:** Accepted
**Decision:** `knowledge_sources.chatbot_id` is required; chunks carry `chatbot_id` for direct filtering.
**Alternatives:** Org-level knowledge bases attached M:N to chatbots: more flexible and avoids duplicate embedding, but adds join-filtered retrieval, more complex permissions and UI.
**Consequences:** Simple retrieval and mental model. Orgs that need the same docs in two bots upload twice (costs embeddings). Migration path: introduce `knowledge_bases`, move `chatbot_id` → `knowledge_base_id` on sources/chunks, back-fill one KB per chatbot, add a link table.

### ADR-012 — Embedding model & dimension
**Status:** Proposed (Q-07, Q-17)
**Decision:** Default `text-embedding-3-small` at 1536 dims (or equivalent via the abstraction), stored as `halfvec(1536)` if eval confirms. `chatbots.embedding_model` records the model per bot; model switches happen via a background re-embed into a shadow column and an atomic swap.
**Alternatives:** Larger 3072-d model (better recall, 2× storage, HNSW limit considerations), open-source models via vLLM (cost control, ops burden), per-tenant model choice (complex index management).
**Consequences:** Dimension is effectively a schema decision. Changing it requires a migration plus a re-embed of all chunks, budgeted as a background job.

### ADR-013 — Structure-aware recursive chunking (512-token target)
**Status:** Accepted (tunable via eval)
**Decision:** Split by headings → paragraphs → sentences; target 512 tokens, max 800, overlap 64; contextual header prepended to the embedded text; page and heading metadata kept.
**Alternatives:** Fixed-size windows (simpler, worse coherence), semantic chunking via embeddings (costly at ingest, marginal gains), LLM-based "contextual retrieval" summaries per chunk (strong quality but high ingest cost — candidate post-MVP for higher tiers).
**Consequences:** Good default for policy/help-centre content. Parameters live in config and eval guards changes.

### ADR-014 — Hybrid retrieval (vector + Postgres FTS, RRF); reranker post-MVP
**Status:** Proposed (Q-16)
**Decision:** Vector leg is P0. FTS leg with RRF fusion is added in P3 if eval shows benefit. Diversity cap of 2 chunks per document. Relevance gate on top cosine score.
**Alternatives:** Vector-only (misses exact terms like SKUs/error codes); cross-encoder reranker (best quality, +100–300 ms and cost; post-MVP); external search engine (unnecessary).
**Consequences:** Strong quality from within Postgres. The FTS language config per chatbot must be set correctly (`simple` default for multilingual).

### ADR-015 — OpenAI-compatible LLM provider abstraction; Platform-managed keys
**Status:** Proposed (Q-07)
**Decision:** `ChatModel` / `EmbeddingModel` protocols with one `OpenAICompatibleProvider` (configurable `base_url`), a model registry with costs and limits, retries, a circuit breaker and a fallback chain. Platform pays and recovers cost via plans. BYO keys post-MVP.
**Alternatives:** LangChain/LlamaIndex as the core (fast prototyping, but heavy abstractions, churn and harder debugging; we may borrow loaders selectively); LiteLLM SDK (good, but an extra dependency when the OpenAI SDK + `base_url` covers it; can run LiteLLM *proxy* as a provider if multi-vendor routing is needed).
**Consequences:** Provider portability for any vendor exposing the OpenAI API. Non-compatible vendors need an adapter or proxy.

### ADR-016 — Strict grounding on by default
**Status:** Accepted
**Decision:** Without relevant context, the bot returns the tenant's fallback message. Tenants may disable strict mode (answers then carry a disclaimer and `grounded=false`).
**Consequences:** Fewer hallucinations at the cost of more "I don't know"s, which feed the unanswered-questions loop (a product feature, not a bug).

### ADR-017 — Stripe for billing; Platform owns entitlements and usage
**Status:** Proposed (Q-05)
**Decision:** Stripe Checkout + Customer Portal + Billing (+ Stripe Tax). Webhooks are verified, stored and processed idempotently with state re-fetch; a daily reconciliation job runs. Entitlements = plan limits ⊕ overrides, computed by the Platform.
**Alternatives:** Merchant of Record (Paddle/Lemon Squeezy) handles global tax/VAT liability with a different webhook model and fees; a custom billing engine was rejected.
**Consequences:** Clear split: money in Stripe, limits in our DB. The billing module interface isolates the provider if Q-05 changes.

### ADR-018 — Message credits as the quota unit; hard cap, no overage in MVP
**Status:** Proposed (Q-08, Q-13)
**Decision:** 1 credit = 1 assistant reply (any channel, including playground). Tokens are metered for COGS/abuse but not billed. Hard stop at 100% with a friendly unavailable message. 80%/100% notifications.
**Alternatives:** Token-based billing (precise but opaque to SMB buyers), conversation-based billing (gameable by long conversations), soft limits with overage (revenue upside, but needs metered billing and surprise-bill handling).
**Consequences:** Predictable for customers. Margin risk on long answers is controlled by output token caps and per-tier model choice.

### ADR-019 — Telegram via customer-owned bot tokens and webhooks
**Status:** Accepted (scope timing Q-06)
**Decision:** Customers create bots with BotFather and paste the token; the Platform registers a webhook with `secret_token` at `/webhooks/telegram/{connection_id}`. Private chats only; text only.
**Alternatives:** A single Platform-owned bot routing by deep-link (no per-tenant branding; confusing); long polling (needs persistent workers per bot; doesn't scale).
**Consequences:** Tenant branding and isolation per bot, with minimal infra.

### ADR-020 — WhatsApp via Meta Cloud API, post-MVP
**Status:** Proposed (Q-09)
**Decision:** Cloud API with a platform Meta app and Embedded Signup as the target; manual-connect fallback using the same adapter. Reply only within the 24-hour window initially. Phone numbers hashed and encrypted.
**Alternatives:** BSPs (Twilio, 360dialog — faster onboarding, per-message markup, another vendor and DPA); on-prem API (deprecated by Meta).
**Consequences:** External approval is on the critical path for v1.1, so the application must start during P5.

### ADR-021 — Next.js dashboard calls the API directly; typed client from OpenAPI
**Status:** Accepted
**Decision:** The web app is a UI layer. Data comes via TanStack Query and the generated `openapi-fetch` client with credentials. Server Components may fetch with forwarded cookies for initial render, but there is no business logic, DB access or second auth system in Next.js.
**Alternatives:** A BFF in Next.js (duplicated authz logic and two backends to secure); tRPC (TypeScript-only, doesn't fit a Python backend).
**Consequences:** A single source of truth for authorization (FastAPI). The contract drift check keeps types honest.

### ADR-022 — Managed containers, no Kubernetes for MVP
**Status:** Proposed (Q-02)
**Decision:** Container platform (ECS Fargate / Cloud Run / Render / Fly) + managed Postgres with pgvector + managed Redis + S3-compatible storage + CDN. IaC (Terraform or the platform's blueprint).
**Alternatives:** Kubernetes (flexible, but heavy ops for 2–4 engineers); VPS with docker-compose (cheap, but weak HA, manual ops).
**Consequences:** Low ops burden. Per-queue worker scaling is supported by separate services. Re-evaluate at > ~20 services or multi-region.

### ADR-023 — Python stack details
**Status:** Accepted
**Decision:** Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.1 (async in API, sync in workers) with psycopg 3, Alembic, `uv` for dependencies/locking, Ruff, mypy (strict), structlog, OpenTelemetry, `argon2-cffi`, `openai` SDK, `pypdf`/`pdfplumber`, `python-docx`, `trafilatura`, `httpx2`. Later-phase libraries are added only when the phase that needs them starts.
**Consequences:** A modern, typed and fast toolchain, with a lockfile for reproducible builds.
**Phase 0 note (2026-11-21):** Built on Python 3.13 (not 3.12) and SQLAlchemy 2.1, the current stable lines with full wheel coverage. PostgreSQL 18 image (`pgvector/pgvector:0.8.7-pg18`), which provides native `uuidv7()` (ADR-006). Exact pins are in `services/api/pyproject.toml`.

### ADR-024 — Monorepo with pnpm workspaces; cross-platform scripts
**Status:** Accepted (revised 2026-11-21: Turborepo deferred)
**Decision:** Single repo; pnpm workspaces with `pnpm -r` for cross-package tasks; root `package.json` scripts as the developer interface; Node/Python scripts for cross-platform tasks. No hard dependency on `make`/bash (developers use Windows — PRD §12). Layout: `apps/` (web, widget), `services/api`, `packages/` (ui, shared-types), `infrastructure/` (ARCHITECTURE §5). Turborepo was dropped from Phase 0 as an unnecessary dependency at this size. Add it when CI build times justify task caching.
**Alternatives:** Turborepo now (caching we don't need yet), Nx (more features, more weight), polyrepo (contract drift, harder coordinated changes).
**Consequences:** Atomic cross-stack changes (API + client + UI in one PR). CI splits TS and Python into parallel jobs.

### ADR-025 — Data retention defaults
**Status:** Proposed (Q-14)
**Decision:** Per DATABASE §6: plan-based conversation retention (tenant can shorten), soft-delete grace for orgs (30 days), backups age out ≤ 35 days, minimal webhook payload retention.
**Consequences:** Bounded privacy exposure and storage costs. Must be reflected in the privacy policy and DPA.

### ADR-026 — Supported document formats at launch
**Status:** Proposed (Q-18)
**Decision:** P0: text PDF, DOCX, TXT, MD. P1: HTML, CSV. OCR, PPTX, XLSX post-MVP.
**Consequences:** A small parser attack surface and predictable quality. Scanned PDFs get a clear `no_text` error.

### ADR-027 — Email via provider interface
**Status:** Proposed (Q-10)
**Decision:** `EmailSender` protocol with SMTP (Mailpit) for dev and a provider SDK in prod. Templates live in the repo (MJML or React Email compiled to HTML). Dedicated sending subdomain with SPF/DKIM/DMARC.

### ADR-028 — Observability stack
**Status:** Accepted
**Decision:** structlog JSON + OpenTelemetry traces/metrics (OTLP to a vendor chosen with Q-02) + Sentry for errors. LLM call telemetry is stored on our own `messages` rows; a dedicated LLM-observability tool (e.g. Langfuse) is optional post-MVP.

### ADR-029 — REST + OpenAPI 3.1, Problem Details errors, cursor pagination
**Status:** Accepted
**Decision:** Per API_SPEC §1. The generated TS client and `oasdiff` breaking-change checks run in CI.
**Alternatives:** GraphQL (flexible, but harder to rate-limit/authorize per field, more tooling); gRPC (not browser-friendly).

### ADR-030 — Application-level envelope encryption for secrets
**Status:** Accepted
**Decision:** AES-256-GCM with per-record data keys wrapped by a KMS master key (env key in dev); `key_id` stored for rotation; never return secrets after creation.

### ADR-031 — Single region at launch
**Status:** Proposed (Q-04)
**Decision:** One production region. The data model carries no region assumptions, so a second, fully separate regional deployment (separate DB, separate Stripe customer mapping) is possible later. Tenants are pinned to a region at signup.
**Consequences:** Simple ops. EU residency demands may force an EU-first choice.

### ADR-032 — End-user identity is pseudonymous
**Status:** Accepted
**Decision:** End users are identified by channel-scoped identifiers stored as HMAC hashes, plus encrypted values only where needed to reply. The widget has no login; signed identity (`identify(user_hash)`) is post-MVP.
**Consequences:** Minimal PII. DSR erase works by channel identity. No cross-channel identity linking in MVP.

---

### ADR-033 — Phase 1 identity and tenancy implementation choices
**Status:** Accepted
**Decisions:**
- **No auth caching yet.** Sessions and memberships are read from Postgres on every request (indexed lookups), so logout, password reset, role change and removal apply on the next request. The 60 s Redis caches in ARCH §14 are deferred until measured need.
- **Tenant context is derived, never accepted.** `app.current_user_id` comes from the validated session row; `app.current_org_id` is set only from a membership row the database returned for that user. Both are `set_config(..., true)` (transaction-local).
- **RLS shape.** `memberships` INSERT is limited to self-join (`user_id = current user`), `audit_logs` is append-only for the runtime role, `organizations` has no DELETE policy, and a trigger enforces last-owner and immutable membership identity. Definer functions read FORCE-RLS tables through explicit read-only policies for the owner role (no BYPASSRLS role is created yet).
- **Rate limits fail closed.** If Redis is unreachable, auth endpoints answer 503 instead of dropping brute-force protection.
- **Email is sent in-process after the response** (FastAPI background task), not through Celery, so one-time tokens never transit the broker.
- **Auth events are structured security logs**, not tenant audit rows, because they have no organization context; tenant actions write `audit_logs`.
**Consequences:** Simple, instantly consistent authorization at the cost of one or two indexed queries per request. See `docs/PHASE2_SECURITY_REVIEW.md` for residual risks.

## Part C — Recorded assumptions

Duplicated from [PRD §11](PRD.md#11-assumptions) for convenience. Changing any of these triggers a review of the linked ADRs.

| # | Assumption | Linked |
|---|---|---|
| A1 | SMB self-serve first | Q-03, ADR-005 |
| A2 | English dashboard; multilingual answers | Q-25 |
| A3 | Single region at launch | ADR-031, Q-04 |
| A4 | Platform-managed LLM keys | ADR-015 |
| A5 | Text-based documents dominate | ADR-026 |
| A6 | Server-rendered target websites | ARCH §8.4 |
| A7 | 2–4 engineer team | ADR-001, ADR-022 |
| A8 | Stripe available to the company | ADR-017, Q-05 |
| A9 | Tenants responsible for content lawfulness and end-user notices | SECURITY §13 |
| A10 | Telegram usage is 1:1 private chats | ADR-019 |
