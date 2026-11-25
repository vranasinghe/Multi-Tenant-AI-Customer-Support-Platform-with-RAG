# Product Requirements Document — AI Customer Support Chatbot SaaS

| Field | Value |
|---|---|
| Status | Draft v0.1 — for review |
| Date | 2026-11-21 |
| Companion docs | [ARCHITECTURE](ARCHITECTURE.md) · [DATABASE](DATABASE.md) · [API_SPEC](API_SPEC.md) · [SECURITY](SECURITY.md) · [ROADMAP](ROADMAP.md) · [DECISIONS](DECISIONS.md) |

Working product name: **"the Platform"** (final name pending — see DECISIONS Q-01).

---

## 1. Vision

Give any business a support assistant that answers customers **only from that business's own approved knowledge**, on the channels customers already use (website, Telegram, WhatsApp). Setup takes minutes, the business can see what was answered and why, and costs stay predictable for both the business and the Platform.

## 2. Problem

- Support teams answer the same questions again and again, while the answers already sit in PDFs, help pages and policy documents.
- Generic LLM chatbots *hallucinate*: they make up refund policies, prices and promises. For a business that is a legal and reputational risk.
- Existing tools are either enterprise-priced or hard to set up, and few show *which source* an answer came from.

## 3. Target users

| Persona | Description | Primary jobs |
|---|---|---|
| **Org Owner** (SMB founder, Head of Support) | Signs up, pays, owns the org | Set up bot fast, control cost, trust answers |
| **Admin** | Ops / support lead | Manage team, channels, domains, billing visibility |
| **Agent** | Support/content staff | Maintain knowledge, tune bot behaviour, review conversations |
| **Viewer** | Manager, analyst | Read conversations & analytics |
| **End user** | The business's customer | Get a correct answer quickly, in their language, on their channel |
| **Platform operator** (internal) | Our staff | Support tenants, handle abuse, monitor cost & health |

**Primary market assumption:** SMB and mid-market businesses (1–200 employees), self-serve signup, English-first UI. Enterprise needs (SSO/SAML, data residency, custom contracts) come after the MVP. See DECISIONS Q-03.

## 4. Goals, non-goals, anti-goals

**Goals (MVP)**
1. Self-serve: a new org reaches a working, embedded, grounded chatbot in **< 15 minutes**.
2. Grounded answers with citations. When the knowledge does not cover a question, the bot says so rather than inventing an answer.
3. Hard tenant isolation. One org's data, documents or answers can never reach another org.
4. Predictable cost through plan quotas, metering and hard limits.
5. Visibility through conversation history, feedback and an "unanswered questions" list that tells the business what knowledge to add.

**Non-goals (MVP)**
- Agentic actions (refunds, order lookup, CRM writes, tool calling).
- Live human-agent inbox / handoff (post-MVP; MVP offers a "contact us" fallback message only).
- Voice, email-ticket channels, Slack/Discord/Messenger channels.
- Custom fine-tuning of models.
- On-prem / single-tenant deployments.
- Native mobile apps for the dashboard.

**Anti-goals** (a release that does any of these has failed, even if it "works")
- A bot answers with information from another tenant's knowledge.
- A bot confidently states policy that is not in the tenant's sources (when strict grounding is on).
- A public widget key can be abused to run up unbounded LLM cost for a tenant or for the Platform.
- Customer end-user PII leaks into logs, analytics exports or third parties beyond the declared subprocessors.
- Developer workflow is so slow or flaky that engineers routinely skip tests.

## 5. Success metrics

| Metric | MVP target | Measured by |
|---|---|---|
| Time-to-first-answer (signup → playground answer) | p50 < 10 min | product events |
| Activation (org embeds widget or connects channel within 7 days) | ≥ 35% of verified signups | product events |
| Grounded answer rate (answers with ≥1 citation / all answers) | ≥ 80% on tenant traffic | `messages.grounded` |
| Thumbs-up ratio (of rated answers) | ≥ 75% | `message_feedback` |
| Hallucination rate on internal eval set | < 3% | offline eval harness |
| Chat first-token latency (widget) | p95 < 2.5 s | traces |
| Ingestion: 50-page text PDF to "ready" | p95 < 2 min | job timings |
| Cross-tenant leakage incidents | **0** | tests + audits |
| LLM COGS per message | below plan price margin target (TBD Q-08) | usage events |

## 6. Scope: MVP vs post-MVP

Priority: **P0** = MVP launch blocker, **P1** = in MVP if on schedule (can slip to v1.1 without blocking launch), **P2** = post-MVP.

| Area | Capability | Priority | Phase |
|---|---|---|---|
| Identity | Email + password signup, email verification, login/logout, password reset | P0 | 1 |
| Identity | Session list & revoke | P1 | 1 |
| Identity | Google OAuth sign-in | P2 | post |
| Identity | TOTP MFA | P2 | post |
| Identity | SAML/OIDC SSO, SCIM | P2 | post |
| Tenancy | Create org, multiple orgs per user, org switcher | P0 | 1 |
| Tenancy | Invite members by email with role; change role; remove | P0 | 1 |
| Tenancy | Ownership transfer; org deletion with grace period | P1 | 1 / 9 |
| Tenancy | Audit log (write in MVP; UI view P1) | P0 / P1 | 1 / 7 |
| RBAC | Fixed roles: owner, admin, agent, viewer | P0 | 1 |
| RBAC | Custom roles, per-chatbot permissions | P2 | post |
| Chatbots | Create/edit/pause/archive multiple chatbots | P0 | 2 |
| Chatbots | Instructions, tone, welcome & fallback messages, model choice (allowlist) | P0 | 2 |
| Chatbots | Playground with streaming + citations | P0 | 3 |
| Knowledge | Upload PDF (text-based), DOCX, TXT, MD | P0 | 2 |
| Knowledge | HTML, CSV upload | P1 | 2 |
| Knowledge | Manual Q&A / text snippets | P1 | 2 |
| Knowledge | Website ingestion: single URL, sitemap, bounded crawl | P0 | 4 |
| Knowledge | Manual re-sync of website source | P0 | 4 |
| Knowledge | Scheduled re-crawl, JS-rendered pages | P2 | post |
| Knowledge | OCR for scanned PDFs/images, PPTX, XLSX | P2 | post |
| Knowledge | Shared knowledge bases across chatbots | P2 | post |
| RAG | Vector retrieval with tenant/chatbot filter, citations, strict grounding | P0 | 3 |
| RAG | Hybrid (vector + full-text) retrieval with RRF | P1 | 3 |
| RAG | Follow-up question rewriting with history | P0 | 3 |
| RAG | Cross-encoder reranking | P2 | post |
| RAG | Offline evaluation harness (golden sets) | P0 (internal) | 3 |
| Widget | JS snippet + iframe widget, streaming, mobile-friendly | P0 | 5 |
| Widget | Allowed domains + domain verification | P0 | 5 |
| Widget | Theme: color, title, avatar, position, launcher text | P0 | 5 |
| Widget | Remove "Powered by" branding (paid plans) | P1 | 5 |
| Widget | Bot protection challenge (Turnstile) | P2 | post |
| Channels | Telegram (customer's own bot token) | P1 | 8 |
| Channels | WhatsApp Cloud API | P2 | post (v1.1) |
| Conversations | List, filter, view transcript with sources & feedback | P0 | 7 |
| Conversations | Unanswered questions list | P0 | 7 |
| Conversations | Delete conversation / end-user data (DSR) | P0 | 9 |
| Conversations | CSV export | P1 | 7 |
| Conversations | Human handoff / live inbox | P2 | post |
| Analytics | Per-chatbot dashboard: conversations, messages, grounded rate, feedback, usage | P0 | 7 |
| Billing | Plans, Stripe Checkout, Customer Portal, webhooks | P0 | 6 |
| Billing | Metering & hard quota enforcement, 80%/100% notifications | P0 | 6 |
| Billing | Free trial | P0 | 6 |
| Billing | Metered overage billing | P2 | post |
| Platform | Internal admin via audited CLI commands | P0 | 9 |
| Platform | Internal admin web console | P2 | post |
| Platform | Public REST API with org API keys; outbound webhooks | P2 | post |
| Platform | BYO LLM API key | P2 | post |
| Platform | i18n of dashboard UI | P2 | post |

**MVP definition:** every P0 row ships, plus Phase 9 hardening (load tests, backups/restore drill, security review, privacy flows). P1 items ship if they are on schedule.

## 7. Key user journeys (MVP)

**J1 — Onboard and get a working bot**
1. Owner signs up → verifies email → names org (first org is created automatically).
2. Creates chatbot "Support Bot" → uploads 3 PDFs and adds `https://example.com/help` sitemap.
3. Sees per-document progress (queued → processing → ready, or failed with a readable reason).
4. Asks questions in the playground → gets streamed answers with numbered citations that link to the sources.
5. Adds `example.com` to allowed domains → verifies via meta tag or DNS TXT → copies embed snippet → widget works on site.

**J2 — Team collaboration**
Owner invites `alice@` as Agent → Alice accepts (signs up if new) → Alice can edit knowledge and bot settings but cannot see billing or invite members.

**J3 — End user asks a question (widget)**
Visitor opens widget → sees welcome message → asks "What's your refund window?" → gets a streamed, cited answer → clicks 👎 with reason "outdated" → the business sees it in Conversations and Analytics.

**J4 — Knowledge gap loop**
Agent opens "Unanswered questions" → sees "Do you ship to Canada?" asked 14 times with fallback answers → adds a Q&A snippet → future answers are grounded.

**J5 — Quota and billing**
Org on trial reaches 80% of message credits → owner gets an email and a dashboard banner → upgrades via Stripe Checkout → limits rise immediately after the webhook. At 100% without an upgrade, the widget shows a configurable "temporarily unavailable" message. It never shows an error stack, and it never answers without metering.

**J6 — Telegram (P1)**
Admin creates a bot via BotFather → pastes the token → Platform validates it and registers a webhook → users chatting with the Telegram bot get grounded answers, and the conversations appear in the dashboard tagged "Telegram".

## 8. Functional requirements

Each requirement has an ID so ROADMAP acceptance criteria can refer to it.

### 8.1 Identity & access (AUTH)
- **FR-AUTH-1** Signup with email, password (min 10 chars, breached-password check), name.
- **FR-AUTH-2** Email verification required before creating chatbots or inviting members (login is allowed beforehand).
- **FR-AUTH-3** Login/logout; sessions expire after 14 days of inactivity (absolute 30 days); "log out everywhere".
- **FR-AUTH-4** Password reset via single-use, 30-minute email link; resetting revokes all sessions.
- **FR-AUTH-5** Login and reset endpoints are rate-limited and return no hint about whether an account exists.

### 8.2 Organizations & members (ORG)
- **FR-ORG-1** A user can belong to many orgs; every dashboard request runs in exactly one org context.
- **FR-ORG-2** Invitations by email with a role; 7-day expiry; resend/revoke; accept flow works for new and existing users; an invitation is bound to the invited email address.
- **FR-ORG-3** Change member role, remove member; an org always has ≥ 1 owner; the last owner cannot leave or be demoted.
- **FR-ORG-4** Ownership transfer (owner → existing admin).
- **FR-ORG-5** Org deletion: owner-only, re-authentication required, 30-day soft-delete grace, then irreversible purge (DB rows, files, vectors, Stripe subscription cancelled).
- **FR-ORG-6** Security-relevant actions are written to an append-only audit log.

### 8.3 Chatbots (BOT)
- **FR-BOT-1** CRUD chatbots; plan limits the number of active chatbots.
- **FR-BOT-2** Configurable fields: name, instructions (≤ 4,000 chars), tone preset, welcome message, fallback message, contact/escalation text, response language mode (auto-mirror or fixed), model (from Platform allowlist), strict grounding (default on).
- **FR-BOT-3** Status: draft, active, paused, archived. Paused/archived bots reject public traffic with a friendly message.
- **FR-BOT-4** The playground behaves exactly like production (same pipeline), is marked `channel=playground`, and does not count toward analytics. It does count toward usage (see DECISIONS ADR-018).

### 8.4 Knowledge (KB)
- **FR-KB-1** Upload files: PDF, DOCX, TXT, MD (P0); HTML, CSV (P1). Max file size per plan (default 20 MB); total storage per plan.
- **FR-KB-2** Files are validated by magic bytes, not just extension. Encrypted PDFs, macros and zip bombs are rejected with clear errors.
- **FR-KB-3** Website source: start URL or sitemap URL, same-registrable-domain restriction, include/exclude path patterns, max pages per plan, robots.txt respected.
- **FR-KB-4** Manual text / Q&A snippet source (P1).
- **FR-KB-5** Per-document status: `pending → queued → processing → ready | failed`, with an error code, a human-readable message and a retry action.
- **FR-KB-6** Deleting a document or source removes its chunks/vectors from retrieval **immediately** (in the same transaction) and its files within 24 h.
- **FR-KB-7** Re-uploading identical content (same hash) is detected and skipped; replacing a document re-indexes atomically (old chunks keep serving until the new version is ready).

### 8.5 Chat & RAG (CHAT)
- **FR-CHAT-1** Answers draw only on chunks belonging to the same chatbot (and therefore the same org).
- **FR-CHAT-2** Answers include citations (source title + URL/filename + page where known).
- **FR-CHAT-3** Streaming responses (token-by-token) on widget and playground.
- **FR-CHAT-4** Multi-turn: follow-up questions are resolved with conversation history (bounded window).
- **FR-CHAT-5** With strict grounding on and no sufficiently relevant context, the bot replies with the configured fallback message, and the message is flagged `grounded=false`.
- **FR-CHAT-6** The bot replies in the user's language by default (when the model supports it), even when the sources are in another language.
- **FR-CHAT-7** End users can rate any assistant message 👍/👎, optionally with a reason and comment.
- **FR-CHAT-8** Max user message length 2,000 chars; max answer length bounded by tokens.

### 8.6 Widget (WID)
- **FR-WID-1** Single `<script>` snippet; loads asynchronously; < 10 KB loader; does not block host page rendering.
- **FR-WID-2** Works only on verified allowed domains (plus `localhost` when "test mode" is toggled by an agent).
- **FR-WID-3** Theming: primary color, bot name, avatar, launcher position, launcher label, welcome message.
- **FR-WID-4** Conversation persists across page loads on the same site (visitor ID stored in iframe storage).
- **FR-WID-5** Accessible (WCAG 2.1 AA: keyboard, focus management, ARIA live region for streamed text, contrast).
- **FR-WID-6** No cookies are required; the widget works with third-party cookies blocked.

### 8.7 Channels (CH)
- **FR-CH-1** Telegram: connect with bot token, validate via `getMe`, automatic webhook registration, disconnect (webhook removed), private chats only in MVP, `/start` and `/reset` commands.
- **FR-CH-2** WhatsApp (post-MVP): connect a WhatsApp Business phone number; reply within the 24-hour customer-service window; text messages only at first.
- **FR-CH-3** Channel health: last event time, last error, status (`active | error | disconnected`).

### 8.8 Conversations & analytics (CONV / AN)
- **FR-CONV-1** List conversations with filters: chatbot, channel, date range, feedback (👍/👎), grounded/ungrounded; full-text search on messages (P1).
- **FR-CONV-2** Transcript view showing citations, feedback, model and latency per message (latency for agents and above).
- **FR-CONV-3** Unanswered questions: ungrounded user questions clustered by similarity (MVP: simple grouping by normalized text + embedding similarity, top 50).
- **FR-CONV-4** Delete a conversation; delete all data for an end user (by visitor/channel identity).
- **FR-AN-1** Per-chatbot and org-wide metrics over a selectable range: conversations, messages, grounded rate, 👍/👎 ratio, average/p95 first-token latency, channel breakdown, usage vs quota.

### 8.9 Billing (BILL)
- **FR-BILL-1** Plan catalog with entitlements (chatbots, members, message credits/month, storage, website pages, channels, branding removal).
- **FR-BILL-2** Upgrade/downgrade via Stripe Checkout; manage payment methods/invoices via Stripe Customer Portal.
- **FR-BILL-3** Free trial (default 14 days, no card) with trial limits.
- **FR-BILL-4** Real-time quota enforcement for message credits; notifications at 80% and 100%.
- **FR-BILL-5** Payment failure → `past_due` with a 7-day grace period → restricted mode (dashboard readable; public chat disabled).
- **FR-BILL-6** Downgrade over limit: existing resources are kept but read-only; the org must reduce usage before creating more.
- **FR-BILL-7** Only owners can change plans; admins can view billing.

## 9. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| NFR-1 | Availability | Public chat API 99.9% monthly (excluding upstream LLM outages, which degrade to fallback message); dashboard 99.5% |
| NFR-2 | Latency | Widget first token p95 < 2.5 s; dashboard API p95 < 300 ms (non-LLM endpoints) |
| NFR-3 | Throughput (MVP sizing) | 1,000 orgs, 3,000 chatbots, 10M chunks, 50 chat req/s peak, 20 concurrent ingestion jobs |
| NFR-4 | Isolation | Tenant isolation enforced at DB (RLS) **and** application layers; automated cross-tenant tests in CI |
| NFR-5 | Security | OWASP ASVS L2 targeted; secrets encrypted at rest; TLS 1.2+ everywhere |
| NFR-6 | Privacy | GDPR-ready: DPA, subprocessor list, retention controls, DSR (export/delete) within 30 days |
| NFR-7 | Durability | PITR backups, RPO ≤ 15 min, RTO ≤ 4 h; quarterly restore drill |
| NFR-8 | Accessibility | Dashboard and widget WCAG 2.1 AA |
| NFR-9 | Browser support | Last 2 versions of Chrome, Edge, Firefox, Safari; widget also iOS Safari 16+, Android Chrome |
| NFR-10 | Maintainability | Backend ≥ 80% line coverage on domain/services; type-checked (mypy strict on new modules, TS strict); one-command local setup |
| NFR-11 | Observability | Structured logs, traces, metrics, error tracking; every request carries `request_id`, `org_id` where applicable |
| NFR-12 | Cost | Per-message LLM + embedding cost recorded; Platform-wide daily spend alerting |
| NFR-13 | Portability | Runs on any container host with Postgres 16+ (pgvector ≥ 0.8), Redis 7+, S3-compatible storage |

## 10. Plans (illustrative placeholders, pricing TBD — DECISIONS Q-08)

| Entitlement | Trial (14 d) | Starter | Growth | Business |
|---|---|---|---|---|
| Active chatbots | 1 | 2 | 5 | 20 |
| Members | 2 | 3 | 10 | 30 |
| Message credits / month | 200 | 2,000 | 10,000 | 50,000 |
| Knowledge storage | 50 MB | 500 MB | 2 GB | 10 GB |
| Website pages (indexed, total) | 100 | 1,000 | 5,000 | 25,000 |
| Max file size | 10 MB | 20 MB | 50 MB | 50 MB |
| Channels | Widget | Widget, Telegram | + WhatsApp | + WhatsApp |
| Remove branding | — | — | ✓ | ✓ |
| Conversation retention | 30 d | 90 d | 1 y | 2 y (configurable) |

*Message credit* = one assistant reply delivered to an end user or playground (see ADR-018).

## 11. Assumptions

| # | Assumption | If wrong… |
|---|---|---|
| A1 | Self-serve SMB market first; enterprise later | SSO, data residency and audit exports move into MVP |
| A2 | English-first dashboard; bot answers multilingual via LLM | i18n framework needed in Phase 0 |
| A3 | One production region at launch (EU or US — Q-04) | Multi-region data model needed early |
| A4 | Platform pays for LLM usage (managed keys) and recovers cost via plans | BYO-key path and per-tenant provider config move into MVP |
| A5 | Text-based documents dominate; scanned PDFs are rare | OCR pipeline (and cost) moves into MVP |
| A6 | Most target sites render meaningful HTML server-side | Headless-browser crawling needed in MVP |
| A7 | A small team (2–4 engineers) builds and runs this | Microservices or Kubernetes would be a net negative; reinforces the modular monolith |
| A8 | Stripe is available in the company's country of incorporation | Merchant-of-record provider (Paddle/Lemon Squeezy) instead |
| A9 | Businesses are responsible for the lawfulness of the content they upload and for end-user notices on their sites | More platform-side content moderation and consent tooling |
| A10 | Telegram usage is mostly 1:1 private chats | Group-chat behaviour and privacy-mode handling needed |

## 12. Constraints

- Mandated stack: Next.js + TypeScript + Tailwind + shadcn/ui; FastAPI; PostgreSQL + pgvector; Redis + Celery; S3-compatible storage; OpenAI-compatible LLM APIs; Docker; GitHub Actions; Pytest, Vitest, Playwright.
- Modular monolith; no microservices unless an ADR justifies one.
- Developers work on Windows (and possibly macOS/Linux): the dev workflow must run via Docker Desktop/WSL2 without Unix-only tooling as a hard requirement.

## 13. External dependencies

LLM/embedding provider(s) · Stripe · transactional email provider · Telegram Bot API · Meta WhatsApp Cloud API (post-MVP; requires Meta Business verification — **long lead time, start early**) · DNS resolver for domain verification · S3-compatible object storage · container hosting.

## 14. Glossary

| Term | Meaning |
|---|---|
| Organization (org, tenant) | Billing and isolation boundary; owns chatbots, knowledge, conversations |
| Member | A user's membership in an org with one role |
| Chatbot | A configured assistant with its own knowledge, settings, channels |
| Knowledge source | A file upload, website, or text snippet attached to a chatbot |
| Document | One ingested unit (a file, or one crawled web page) |
| Chunk | A retrievable text segment of a document with its embedding |
| Channel | Delivery surface: widget, playground, Telegram, WhatsApp |
| Channel connection | Credentials + config linking a chatbot to Telegram/WhatsApp |
| End user | A customer of the tenant talking to a chatbot (not a Platform user) |
| Grounded answer | An answer generated with ≥ 1 retrieved chunk above the relevance threshold |
| Message credit | Unit of quota consumption: one assistant reply |
| Public key (`pk_…`) | Non-secret identifier embedded in the widget snippet |
