# API Specification

> Phase 6's public widget issuance, frame/asset endpoints, domain management and retention API are shipped. See [WIDGET_DEPLOYMENT.md](WIDGET_DEPLOYMENT.md) for the current contract and [PHASE6_TEST_REPORT.md](PHASE6_TEST_REPORT.md) for verification. Phase 5's older member-only issuance limitation below is historical.

> Phase 5 implementation note: the conversation and restricted-widget endpoints actually shipped, SSE frames and deviations from the planned contract below are documented in [CHAT_ENGINE.md](CHAT_ENGINE.md). Use that contract for the current playground. The public API does not yet support anonymous session creation from a public key.

| Field | Value |
|---|---|
| Status | Draft v0.1 — contract outline for review; the generated OpenAPI 3.1 document becomes the source of truth from Phase 0 |
| Date | 2026-11-21 |
| Related | [ARCHITECTURE](ARCHITECTURE.md) · [DATABASE](DATABASE.md) · [SECURITY](SECURITY.md) · [ROADMAP](ROADMAP.md) |

---

## 1. Conventions

### 1.1 Surfaces

| Surface | Base URL | Auth | Consumers |
|---|---|---|---|
| Dashboard API | `https://api.example.com/api/v1` | Session cookie `__Host-session` (+ CSRF header) | Next.js dashboard |
| Public widget API | `https://api.example.com/public/v1` | Widget session JWT (`Authorization: Bearer`) | Widget iframe |
| Embed shell | `https://widget.example.com/embed/{public_key}` | none (browser `frame-ancestors`) | Widget loader |
| Webhooks (inbound) | `https://api.example.com/webhooks/...` | Provider signature / secret | Stripe, Telegram, Meta |
| Ops | `/healthz`, `/readyz`, `/metrics` (internal network only) | network policy | Platform |

### 1.2 Format & style

- REST, JSON (`application/json; charset=utf-8`), `snake_case` fields, UTF-8.
- Timestamps are RFC 3339 UTC (`2026-11-21T10:15:00Z`). IDs are UUIDv7 strings.
- Org-scoped resources live under `/orgs/{org_id}/…`. Chatbot-owned resources live under `/orgs/{org_id}/chatbots/{chatbot_id}/…`.
- A resource that exists in another org returns **404**, never 403, so its existence is not revealed.
- `PATCH` uses JSON Merge Patch semantics (omitted = unchanged, `null` = clear where allowed).
- Streaming uses **Server-Sent Events** (`text/event-stream`), see §5.

### 1.3 Pagination

Cursor-based: `?limit=25&cursor=<opaque>` (max `limit` 100).
```json
{ "data": [ ... ], "next_cursor": "eyJpZCI6IjAxOTMuLi4ifQ", "has_more": true }
```
Cursors encode `(sort_key, id)` and are signed (HMAC) to prevent tampering.

### 1.4 Errors — RFC 9457 Problem Details

```json
{
  "type": "https://docs.example.com/errors/quota_exceeded",
  "title": "Monthly message credits exhausted",
  "status": 402,
  "code": "quota_exceeded",
  "detail": "Your organization has used 2000 of 2000 message credits for this period.",
  "request_id": "req_01JD2X...",
  "errors": [ { "field": "name", "code": "too_long", "message": "Must be at most 80 characters" } ]
}
```

| HTTP | `code` examples |
|---|---|
| 400 | `bad_request`, `invalid_cursor` |
| 401 | `unauthenticated`, `session_expired`, `invalid_token` |
| 403 | `forbidden` (authenticated, in org, role lacks permission), `email_not_verified`, `origin_not_allowed`, `org_restricted` |
| 404 | `not_found` |
| 409 | `conflict`, `already_member`, `duplicate_document`, `last_owner`, `channel_already_connected` |
| 402 | `quota_exceeded`, `plan_limit_reached` (with `limit_key`) |
| 413 | `file_too_large` |
| 415 | `unsupported_media_type` |
| 422 | `validation_error` (with `errors[]`) |
| 429 | `rate_limited` (with `Retry-After` header) |
| 502/503/504 | `upstream_unavailable`, `llm_unavailable`, `maintenance` |

### 1.5 Idempotency

`Idempotency-Key: <uuid>` is **accepted on all POSTs** and **required** on: billing checkout/portal sessions, document upload init, invitations, channel connect. The response is replayed for 24 h. If the same key arrives with a different body → `409 idempotency_key_reused`.

### 1.6 Versioning & compatibility

- URL major version (`/v1`). Additive changes (new fields, endpoints, enum values documented as extensible) are non-breaking.
- CI runs `oasdiff breaking` against `main`. Breaking changes require `/v2` or a deprecation window (`Deprecation` + `Sunset` headers, ≥ 90 days for public widget API; the dashboard is deployed in lockstep).
- The widget loader is versioned in its path (`/widget/v1/loader.js`) and is kept compatible with `/public/v1`.

### 1.7 Rate limits (defaults; Redis token buckets)

| Scope | Limit |
|---|---|
| `POST /auth/login` per IP | 10/min, 100/h |
| `POST /auth/login` per email | 5/min, 20/h (then 15-min lockout with email notice) |
| `POST /auth/forgot-password`, `/resend-verification` per email & IP | 3/h |
| Dashboard API per session | 300/min |
| Playground messages per org | 30/min |
| Widget session creation per IP | 20/min |
| Widget messages per session | 10/min, 100 per session lifetime |
| Widget messages per IP | 30/min |
| Widget messages per chatbot | configurable (default 60/min) |
| Webhooks per connection | 50/s (above → 429; providers retry) |

Responses include `RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` (IETF draft headers).

### 1.8 Permissions notation

Each endpoint lists the required permission (see [SECURITY.md §4](SECURITY.md#4-rbac)). `auth` = any authenticated user; `verified` = authenticated with a verified email.

---

## 2. Dashboard API — endpoint catalog

### 2.1 Auth & account (Phase 1)

| Method | Path | Perm | Description |
|---|---|---|---|
| POST | `/auth/signup` | public | Create user + first org; sets session cookie |
| POST | `/auth/login` | public | Create session |
| POST | `/auth/logout` | auth | Revoke current session |
| POST | `/auth/verify-email` | public | Consume verification token |
| POST | `/auth/resend-verification` | auth | Re-send verification email |
| POST | `/auth/forgot-password` | public | Always 202 |
| POST | `/auth/reset-password` | public | Consume reset token; revokes all sessions |
| GET | `/me` | auth | Current user + memberships summary |
| PATCH | `/me` | auth | Update name, locale |
| POST | `/me/password` | auth | Change password (requires current password) |
| GET | `/me/sessions` | auth | List active sessions (P1) |
| DELETE | `/me/sessions/{session_id}` | auth | Revoke a session (P1) |
| DELETE | `/me/sessions` | auth | Log out everywhere except current (P1) |

### 2.2 Organizations, members, invitations (Phase 1)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs` | auth | Orgs the user belongs to |
| POST | `/orgs` | verified | Create org (caller becomes owner) |
| GET | `/orgs/{org_id}` | `org:read` | Org details incl. plan summary |
| PATCH | `/orgs/{org_id}` | `org:update` | Name, settings (retention ≤ plan max) |
| DELETE | `/orgs/{org_id}` | `org:delete` | Schedule deletion (requires `password` re-auth in body); 30-day grace |
| POST | `/orgs/{org_id}/restore` | `org:delete` | Cancel pending deletion |
| POST | `/orgs/{org_id}/transfer-ownership` | `org:transfer` | `{ new_owner_user_id }` (must be admin) |
| GET | `/orgs/{org_id}/members` | `member:read` | List members |
| PATCH | `/orgs/{org_id}/members/{membership_id}` | `member:manage` | Change role (rules in SECURITY §4) |
| DELETE | `/orgs/{org_id}/members/{membership_id}` | `member:manage` / self | Remove member / leave org |
| GET | `/orgs/{org_id}/invitations` | `member:invite` | Pending invitations (least privilege: invited emails are visible to inviters only; revised in Phase 1) |
| POST | `/orgs/{org_id}/invitations` | `member:invite` | `{ email, role }` |
| POST | `/orgs/{org_id}/invitations/{id}/resend` | `member:invite` | |
| DELETE | `/orgs/{org_id}/invitations/{id}` | `member:invite` | Revoke |
| GET | `/invitations/lookup?token=` | public | Org name, inviter name, role, email hint (masked) — rate-limited |
| POST | `/invitations/accept` | verified | `{ token }`; session email must match invitation |
| GET | `/orgs/{org_id}/audit-logs` | `audit:read` | Newest first; `?limit&cursor&action` (shipped in Phase 1; cursor is opaque, not yet signed) |

### 2.3 Chatbots & domains (Phases 2, 5)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}/chatbots` | `chatbot:read` | List |
| POST | `/orgs/{org_id}/chatbots` | `chatbot:write` | Create (plan limit `active_chatbots`) |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}` | `chatbot:read` | Details incl. knowledge stats |
| PATCH | `/orgs/{org_id}/chatbots/{chatbot_id}` | `chatbot:write` | Update config/status/widget settings |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}` | `chatbot:delete` | Soft delete (cascades knowledge after 7 days) |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/rotate-public-key` | `chatbot:write` | New `pk_`; old key invalid immediately |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/test-mode` | `chatbot:write` | `{ enabled }` → localhost allowed for 24 h |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/embed-snippet` | `chatbot:read` | HTML snippet |
| GET | `/orgs/{org_id}/models` | `chatbot:read` | Model allowlist for org's plan |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/domains` | `chatbot:read` | |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/domains` | `domain:manage` | `{ domain, verification_method }` → returns token & instructions |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/domains/{domain_id}/verify` | `domain:manage` | Run check now (rate-limited 10/h) |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}/domains/{domain_id}` | `domain:manage` | |

### 2.4 Knowledge (Phases 2, 4)

> **As implemented (2026-11-22):** uploads are `POST …/documents?filename=…` with the file as the raw request body (no presigned flow); only `website` sources are created through `POST …/sources` (body requires `confirm_authorized: true`; the file source is implicit); added `GET …/knowledge/limits`, `POST …/reindex[?force=true]`, `POST …/retrieval/search` (`chatbot:test`; `{query, mode: vector|keyword|hybrid, top_k?, min_score?}`). Not implemented: text sources, `documents/{id}/download`, `replace`, `complete`. See [INGESTION.md](INGESTION.md).

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/sources` | `knowledge:read` | List sources with stats |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/sources` | `knowledge:write` | Create `website` or `text` source |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/sources/{source_id}` | `knowledge:read` | |
| PATCH | `/orgs/{org_id}/chatbots/{chatbot_id}/sources/{source_id}` | `knowledge:write` | Rename; website rules; text content |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}/sources/{source_id}` | `knowledge:write` | Removes all its documents from retrieval immediately |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/sources/{source_id}/sync` | `knowledge:write` | Re-crawl website (max 1 concurrent; cooldown 10 min) |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/uploads` | `knowledge:write` | Init upload → presigned PUT |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}/complete` | `knowledge:write` | Confirm upload; enqueue processing |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/documents` | `knowledge:read` | Filter `source_id`, `status`, search title |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}` | `knowledge:read` | Status, error, counts |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}/chunks` | `knowledge:read` | Paginated chunk preview (debugging) |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}/download` | `knowledge:read` | 302 to presigned GET (5 min) |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}/retry` | `knowledge:write` | Retry failed |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}/replace` | `knowledge:write` | Init new version upload (atomic swap on ready) |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}/documents/{document_id}` | `knowledge:write` | |

### 2.5 Playground (Phase 3)

| Method | Path | Perm | Description |
|---|---|---|---|
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/playground/messages` | `chatbot:test` | SSE stream; body `{ conversation_id?, content }` |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}/playground/conversations/{id}` | `chatbot:test` | Reset |

### 2.6 Conversations & feedback (Phase 7; data captured from Phase 3)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}/conversations` | `conversation:read` | Inbox: `chatbot_id`, `channel`, `status`, `from`, `to`, `feedback`, `satisfaction`, `unanswered`, `grounded=false`, `q`, cursor pagination |
| GET | `/orgs/{org_id}/conversations/{conversation_id}` | `conversation:read` | Transcript, status, CSAT, handoff, events (messages included; retrieval still gated) |
| GET | `/orgs/{org_id}/conversations/{conversation_id}/messages` | `conversation:read` | Earlier transcript pages; `?cursor&limit` (≤100) |
| PATCH | `/orgs/{org_id}/conversations/{conversation_id}` | `conversation:write` | Staff outcome `{ status: open\|resolved\|unresolved }`. An AI reply does not change status. |
| DELETE | `/orgs/{org_id}/conversations/{conversation_id}` | `conversation:delete` | Hard delete transcript; usage and daily aggregates remain |
| PUT | `/orgs/{org_id}/conversations/{conversation_id}/satisfaction` | `conversation:write` | Conversation CSAT `{ score: 1–5, comment? }` |
| POST | `/orgs/{org_id}/conversations/{conversation_id}/handoff` | `conversation:write` | Human handoff request; sets status `handed_off` |
| PATCH | `/orgs/{org_id}/conversations/{conversation_id}/handoff` | `conversation:write` | `{ status: acknowledged\|completed\|cancelled }` |
| POST | `/orgs/{org_id}/conversations/{conversation_id}/unanswered` | `conversation:write` | Mark the latest customer question unanswered |
| GET | `/orgs/{org_id}/unanswered` | `conversation:read` | Grouped unanswered questions (playground excluded) |
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/unanswered` | `conversation:read` | Same grouping, one chatbot |
| GET | `/orgs/{org_id}/knowledge-gaps` | `conversation:read` | Clustered unanswered questions (Jaccard ≥ 0.6) |
| GET | `/orgs/{org_id}/conversation-retention` | `conversation:read` | Effective retention days (default 365, range 1–730) |
| POST | `/orgs/{org_id}/conversations/exports` | `conversation:export` | Build CSV; stored under the org prefix |
| GET | `/orgs/{org_id}/exports/{export_id}` | `conversation:export` | Status + authorized download path (not a public URL) |
| GET | `/orgs/{org_id}/exports/{export_id}/download` | `conversation:export` | Stream CSV; cross-tenant IDs 404 |

### 2.7 Analytics & usage (Phases 6, 7)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}/analytics/summary` | `analytics:read` | Live totals from source events. Playground excluded from product rates. See [analytics-metrics.md](analytics-metrics.md). |
| GET | `/orgs/{org_id}/analytics/timeseries` | `analytics:read` | `?metric=conversations\|resolved\|tokens\|cost&interval=day\|month` |
| GET | `/orgs/{org_id}/usage` | `usage:read` | Current period counters vs limits for all metrics |

### 2.8 Channels (Phases 8, post-MVP)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}/chatbots/{chatbot_id}/channels` | `channel:read` | Connections + health |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/channels/telegram` | `channel:manage` | `{ bot_token }` |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/channels/whatsapp` | `channel:manage` | Embedded Signup code exchange `{ code }` or manual `{ phone_number_id, waba_id, access_token, app_secret }` |
| POST | `/orgs/{org_id}/chatbots/{chatbot_id}/channels/{connection_id}/test` | `channel:manage` | Re-validate credentials & webhook |
| DELETE | `/orgs/{org_id}/chatbots/{chatbot_id}/channels/{connection_id}` | `channel:manage` | Disconnect (deregister webhook, wipe credentials) |

### 2.9 Billing (Phase 6)

| Method | Path | Perm | Description |
|---|---|---|---|
| GET | `/plans` | public | Public plan catalog |
| GET | `/orgs/{org_id}/billing` | `billing:read` | Subscription, plan, status, period, trial end, payment status |
| POST | `/orgs/{org_id}/billing/checkout-session` | `billing:manage` | `{ plan_code, success_path, cancel_path }` → `{ url }` |
| POST | `/orgs/{org_id}/billing/portal-session` | `billing:manage` | `{ return_path }` → `{ url }` |

`success_path`/`return_path` are relative paths only (validated), so they cannot be turned into open redirects.

---

## 3. Detailed contracts (key endpoints)

### 3.1 `POST /api/v1/auth/signup`

Request
```json
{ "email": "owner@acme.com", "password": "correct horse battery", "name": "Dana Lee", "org_name": "Acme Inc" }
```
Response `201` (+ `Set-Cookie: __Host-session=…`)
```json
{
  "user": { "id": "0193…", "email": "owner@acme.com", "name": "Dana Lee", "email_verified": false },
  "org": { "id": "0193…", "name": "Acme Inc", "role": "owner" }
}
```
Errors: `422 validation_error` (weak/breached password, invalid email). An already-registered email gets the **same 201 shape**, with no session cookie and a notification email sent to the existing account, to prevent account enumeration (Q-20 confirms the UX trade-off).

### 3.2 `POST /api/v1/auth/login`

Request `{ "email": "…", "password": "…" }` → `200 { "user": {…}, "orgs": [ { "id", "name", "role" } ] }` + cookie.
Errors: `401 invalid_credentials` (identical for unknown email / wrong password / disabled), `429 rate_limited`.

### 3.3 `POST /api/v1/orgs/{org_id}/invitations`

Request `{ "email": "alice@acme.com", "role": "agent" }` + `Idempotency-Key`
Response `201`
```json
{ "id": "0193…", "email": "alice@acme.com", "role": "agent", "expires_at": "2026-11-28T10:00:00Z", "status": "pending" }
```
Errors: `409 already_member`, `409 conflict` (pending invite exists → use resend), `402 plan_limit_reached` (`limit_key: "members"`, counts pending invites), `403 forbidden` (admin inviting an `admin` is allowed; inviting `owner` is never allowed).

### 3.4 `POST /api/v1/orgs/{org_id}/chatbots`

Request
```json
{
  "name": "Support Bot",
  "instructions": "Help customers of Acme with orders, shipping and returns.",
  "tone": "friendly",
  "welcome_message": "Hi! How can I help?",
  "fallback_message": "I'm not sure about that. Please email support@acme.com.",
  "model": "gpt-4.1-mini",
  "strict_grounding": true
}
```
Response `201`
```json
{
  "id": "0193…", "name": "Support Bot", "status": "draft", "public_key": "pk_live_8fK2…",
  "model": "gpt-4.1-mini", "strict_grounding": true, "retrieval_top_k": 6,
  "widget_settings": { "primary_color": "#4F46E5", "title": "Support Bot", "position": "bottom-right", "show_branding": true },
  "knowledge": { "sources": 0, "documents": 0, "ready": 0 },
  "created_at": "2026-11-21T10:00:00Z"
}
```
(Model ids are examples; the allowlist comes from the model registry — Q-07.)

### 3.5 `POST …/chatbots/{chatbot_id}/documents/uploads`

Request `{ "filename": "refund-policy.pdf", "size_bytes": 482113, "content_type": "application/pdf", "source_id": null }`
(`source_id` null → a `file` source is created automatically, one per upload batch.)

Response `201`
```json
{
  "document": { "id": "0193…", "status": "pending", "source_id": "0193…" },
  "upload": {
    "method": "PUT",
    "url": "https://s3…/orgs/…/original?X-Amz-…",
    "headers": { "Content-Type": "application/pdf" },
    "expires_at": "2026-11-21T10:10:00Z"
  }
}
```
Errors: `413 file_too_large`, `415 unsupported_media_type` (by declared type/extension; re-checked by magic bytes later), `402 plan_limit_reached` (`storage_bytes`, `documents`).

### 3.6 `POST …/documents/{document_id}/complete`

→ `202 { "id": "…", "status": "queued" }`. Errors: `409 conflict` (not in `pending`), `400 upload_missing` / `upload_size_mismatch`.

Document status object (used by list/get):
```json
{
  "id": "0193…", "title": "refund-policy.pdf", "status": "failed",
  "error": { "code": "no_text", "message": "We couldn't find selectable text. This looks like a scanned document." },
  "page_count": 12, "chunk_count": 0, "size_bytes": 482113, "version": 1,
  "updated_at": "2026-11-21T10:03:12Z"
}
```

### 3.7 `POST …/chatbots/{chatbot_id}/sources` (website)

Request
```json
{
  "kind": "website",
  "name": "Help Center",
  "config": {
    "start_url": "https://help.acme.com/",
    "sitemap_url": "https://help.acme.com/sitemap.xml",
    "include": ["/articles/**"],
    "exclude": ["/articles/internal/**"],
    "max_pages": 500,
    "max_depth": 3
  }
}
```
Response `201` with source `status: "syncing"`. Validation: URL must be `http(s)`, public host (SSRF rules), `max_pages ≤` remaining plan allowance.

### 3.8 Playground / widget message (SSE)

`POST /api/v1/orgs/{org_id}/chatbots/{chatbot_id}/playground/messages`
`POST /public/v1/widget/conversations/{conversation_id}/messages`

Request `{ "content": "What is your refund window for international orders?", "client_message_id": "uuid" }`
(`client_message_id` dedupes retries from flaky networks.)

Response `200 text/event-stream` (see §5).

Pre-stream errors return normal JSON problem responses: `402 quota_exceeded`, `403 org_restricted`, `409 chatbot_inactive`, `422 validation_error`, `429 rate_limited`.

### 3.9 `POST /public/v1/widget/sessions`

Request (from the iframe; `Origin: https://widget.example.com`)
```json
{ "public_key": "pk_live_8fK2…", "visitor_id": "c3f1…", "parent_origin": "https://www.acme.com", "locale": "en-US" }
```
Response `200`
```json
{
  "session_token": "eyJhbGciOiJIUzI1NiIsImtpZCI6IncxIn0…",
  "expires_at": "2026-11-21T10:30:00Z",
  "visitor_id": "c3f1…",
  "conversation": { "id": "0193…", "messages": [ { "id": "…", "role": "assistant", "content": "Hi! How can I help?" } ] },
  "config": {
    "title": "Support Bot", "primary_color": "#4F46E5", "avatar_url": null,
    "welcome_message": "Hi! How can I help?", "show_branding": true, "input_max_chars": 2000
  }
}
```
Errors: `403 origin_not_allowed` (parent origin not verified, or test mode off for localhost), `404 not_found` (unknown/rotated key), `409 chatbot_inactive`, `403 org_restricted` (billing), `429 rate_limited`.

Other widget endpoints:

| Method | Path | Description |
|---|---|---|
| POST | `/public/v1/widget/sessions/refresh` | Bearer (≤ 5 min to expiry) → new token |
| POST | `/public/v1/widget/conversations` | Start a new conversation (the "new chat" button) |
| GET | `/public/v1/widget/conversations/{id}/messages` | History for this visitor only (`sub` must match `end_user`) |
| POST | `/public/v1/widget/conversations/{id}/messages` | Send message → SSE |
| POST | `/public/v1/widget/messages/{message_id}/feedback` | `{ rating: 1 \| -1, reason?, comment? }` |
| PUT | `/public/v1/chat/satisfaction` | Bearer session; conversation CSAT `{ score: 1–5, comment? }` |
| POST | `/public/v1/chat/handoff` | Bearer session; `{ reason, contact? }` sets status `handed_off` |

### 3.10 `POST …/channels/telegram`

Request `{ "bot_token": "123456:ABC-DEF…" }` + `Idempotency-Key`
Response `201`
```json
{ "id": "0193…", "type": "telegram", "status": "active", "display_name": "@acme_support_bot", "last_event_at": null }
```
Errors: `422 invalid_credentials` (`getMe` failed), `409 channel_already_connected` (this bot is connected elsewhere — the message doesn't reveal which org), `402 plan_limit_reached` (`channels`). The token is never returned by any endpoint after creation.

### 3.11 `POST /orgs/{org_id}/billing/checkout-session`

Request `{ "plan_code": "growth_monthly_v1", "success_path": "/orgs/0193…/billing?status=success", "cancel_path": "/orgs/0193…/billing" }`
Response `200 { "url": "https://checkout.stripe.com/c/pay/cs_…" }`
Errors: `409 conflict` (already on that plan), `422` (unknown/inactive plan).

### 3.12 `GET /orgs/{org_id}/usage`

```json
{
  "period": { "start": "2026-11-01T00:00:00Z", "end": "2026-12-01T00:00:00Z" },
  "plan": { "code": "starter_monthly_v1", "tier": "starter" },
  "metrics": {
    "message_credits": { "used": 1640, "limit": 2000, "pct": 82 },
    "storage_bytes":   { "used": 120400000, "limit": 524288000 },
    "indexed_pages":   { "used": 310, "limit": 1000 },
    "active_chatbots": { "used": 2, "limit": 2 },
    "members":         { "used": 3, "limit": 3 }
  },
  "status": "warning"
}
```

---

## 4. Inbound webhooks

| Method | Path | Verification | Behaviour |
|---|---|---|---|
| POST | `/webhooks/stripe` | `Stripe-Signature` (timestamp tolerance 5 min), raw body | Insert `billing_events` (dedupe) → enqueue → `200`. Unknown event types → `200` ignored |
| POST | `/webhooks/telegram/{connection_id}` | `X-Telegram-Bot-Api-Secret-Token` constant-time compare | Dedupe `update_id` → enqueue → `200` within 1 s. Unknown/disconnected connection → `200` (avoids retry storms), logged |
| GET | `/webhooks/whatsapp` | `hub.mode=subscribe` + `hub.verify_token` match | Echo `hub.challenge` |
| POST | `/webhooks/whatsapp` | `X-Hub-Signature-256` HMAC-SHA256(app_secret, raw body) | Route by `phone_number_id` → dedupe `wamid` → enqueue → `200` |
| POST | `/webhooks/whatsapp/{connection_id}` | as above with per-connection app secret | Manual-connect mode |

Webhook handlers do no LLM work inline and never return a 5xx for business-logic failures. They return 5xx only for verified-but-unpersistable requests, so the provider retries.

---

## 5. Streaming protocol (SSE)

```
event: message.created
data: {"conversation_id":"0193…","user_message_id":"0193…","assistant_message_id":"0193…"}

event: token
data: {"delta":"Our refund window for international orders is "}

event: token
data: {"delta":"30 days from delivery [1]."}

event: citations
data: {"sources":[{"rank":1,"title":"Refund Policy","uri":"https://help.acme.com/refunds","page":null}]}

event: done
data: {"assistant_message_id":"0193…","grounded":true,"finish_reason":"stop"}
```

- On mid-stream failure: `event: error` `data: {"code":"llm_unavailable","message":"…"}` then the stream closes. The partial assistant message is stored with `status=failed`, and the credit is released.
- When there is no relevant context (strict): a single `token` event with the fallback message, then `done` with `grounded:false`. No citations event.
- Keep-alive comment `: ping` every 15 s. Client disconnect cancels generation (server checks `request.is_disconnected()` and stops pulling from the provider). Credits are still consumed if ≥ 1 token was delivered.
- The widget uses `fetch()` + `ReadableStream` parsing (not `EventSource`) so it can send `Authorization` headers and POST bodies.

---

## 6. Embed snippet

```html
<script async src="https://cdn.example.com/widget/v1/loader.js"
        data-bot-key="pk_live_8fK2…"
        integrity="sha384-…" crossorigin="anonymous"></script>
```
Optional loader API: `window.PlatformChat?.open()`, `.close()`, `.setLocale('fr')`. Post-MVP: `.identify({ user_hash })` for signed end-user identity (HMAC computed on the customer's server).

---

## 7. Phase-to-contract map

| Phase | Endpoints delivered (must appear in OpenAPI with tests) |
|---|---|
| 0 | `/healthz`, `/readyz`, OpenAPI export, generated client package |
| 1 | §2.1, §2.2 |
| 2 | §2.3 (minus domains), §2.4 (file uploads, text sources) |
| 3 | §2.5, internal conversation persistence, `GET …/messages` for playground |
| 4 | §2.4 website sources & sync |
| 5 | §2.3 domains, test mode, embed snippet; §3.9 widget endpoints; embed shell |
| 6 | §2.7 usage, §2.9 billing, `/webhooks/stripe` |
| 7 | §2.6, §2.7 analytics, audit-log list |
| 8 | §2.8 Telegram, `/webhooks/telegram/{id}` |
| 9 | DSR erase, org deletion purge completion, rate-limit tuning |
| post | WhatsApp, org API keys (`/orgs/{id}/api-keys`), outbound webhooks, BYO LLM keys |
