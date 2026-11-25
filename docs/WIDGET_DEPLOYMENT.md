# Phase 6 — Website widget v1.0.0

## Install

In the dashboard, open a chatbot → **Install**. Activate the chatbot before testing public chat. Add each exact website origin, including scheme and nonstandard port. Wildcards and URL paths are not accepted. `www.example.com` and `example.com` are separate origins.

For `https://www.example.com`, create a DNS TXT record named `_acs-widget.www.example.com` with the `acs-widget=…` proof shown in the dashboard, then click **Verify origin**. DNS propagation may delay verification. A proof expires after seven days; click Verify again before expiry. Failed re-verification revokes the old proof. Local/test environments allow explicit verification of localhost/loopback origins without DNS; production does not.

Paste the copyable script before the closing body tag:

```html
<script async src="https://api.example.com/widget/v1/loader.js"
        data-bot-key="pk_live_YOUR_PUBLIC_CHATBOT_KEY"></script>
```

For Next.js, use its Script component with the same public attributes:

```tsx
import Script from "next/script";

<Script src="https://api.example.com/widget/v1/loader.js"
        data-bot-key="pk_live_YOUR_PUBLIC_CHATBOT_KEY"
        strategy="afterInteractive" />
```

Use the API origin as the script host: the loader derives iframe/API URLs from it. Hosting only the JS on an unrelated CDN is insufficient; proxy the widget/frame and public API routes through the same origin. Configure the customer's CSP to allow this script origin in `script-src` and `frame-src`. The host page needs no access to provider secrets or bearer credentials.

The **Live widget preview** runs the same public bundle, session issuance and iframe as a customer site. Verify the dashboard origin as well to use it. Saved branding, name, welcome message, avatar, position and colors are applied; reload the preview after saving changes. Draft, paused, archived or deleted bots do not serve public chat. Copying a public key never grants dashboard access.

## Distribution and rollout

```powershell
corepack pnpm --filter @acs/widget build
docker compose up -d --build --wait
```

The build writes `apps/widget/dist/loader.js` and copies its deployable distribution to `services/api/widget_assets/v1/loader.js`, with `manifest.json` identifying semantic version **1.0.0** and its measured gzip size. The bundle is dependency-free, approximately **4 KB gzipped** (under the enforced 10KB budget), and includes both the host loader and isolated iframe UI. The API exposes `/widget/v1/loader.js` with JavaScript MIME type, nosniff and a one-hour cache. The `v1` path permits compatible updates; keep previous artifacts/images for rollback rather than marking this URL immutable.

Build the widget **before** building the production API image. Its runtime Docker stage includes `widget_assets`. Apply migration **0006** before deploying the new API. It adds a FORCE-RLS-protected `chatbot_domains` table, retention settings and hashed resume credentials. Existing Phase 5 sessions remain compatible. Downgrading drops origin/resumption settings and must be treated as destructive; prefer a forward fix.

Serve everything through HTTPS. Preserve the frame route's per-origin `frame-ancestors` CSP; do not replace it with a wildcard or global DENY header. Do not cache frame or session responses. Disable proxy buffering for SSE and permit the configured chat timeout. Configure trusted proxy addresses correctly before relying on IP limits; the pre-existing production Docker wildcard forwarded-IP setting remains an operational deployment risk (see PHASE2_SECURITY_REVIEW.md). Tenant quotas and session limits also apply independently of IP controls.

No wildcard credentialed CORS was added. Browsers fetch chat from inside the API-hosted iframe using bearer capabilities and `credentials: omit`; customer websites do not need dashboard API CORS access. The sandbox allows scripts and same-origin API access, but no top navigation, popups or forms. Use a dedicated API/widget origin separate from the customer website.

## Sessions and privacy

- The browser receives a random short-lived bearer token scoped to one organization, chatbot and conversation. It is kept in memory. Provider keys are server-only.
- A separate random resume credential is stored only as a hash on the server. The browser stores it under a key containing the exact parent origin and public chatbot key. Different sites/bots therefore have separate histories. Resume rotates the access token; an older tab may need reopening after another tab resumes.
- Dashboard retention is **0–30 days**, default seven. Zero keeps the resume credential in memory only. Expiry, shortening retention, key rotation, removing an allowed origin, verification expiry, pausing a bot and restricting an organization prevent further access. New chat clears the browser resume credential and starts a separate conversation.
- Retention here is a **resumption/access lifetime**, not an automatic database purge promise. Persisted conversations retain the platform's existing database-retention behavior. Configure privacy notices and database deletion/retention operations before a customer launch.
- If third-party storage is blocked, the widget still works with its in-memory session, but reload restoration is unavailable. No third-party cookies are required. Full anonymous cross-device identity is intentionally absent.

## Security boundaries

Verified origins are defense in depth, not strong client authentication: a scripted HTTP client can forge headers and parent-origin claims. The server checks domain proofs before issuing a session and again on public-token use. The browser separately enforces the exact parent origin through CSP. PostMessage resize events require the matching iframe window, API origin and per-instance random identifier, and contain no conversation content or credentials.

Issuance is rate limited per IP, organization conversation creation is limited, each bearer session has rate/lifetime message limits, and Phase 5 organization concurrency, token and dollar caps remain enforced. Refreshing a session does not reset its lifetime message counter. Redis failure is fail-closed. Header checks alone are never used to grant admin permissions.

All messages, welcome text, document titles and model output are rendered with DOM `textContent`. No raw HTML/Markdown is executed. Only HTTPS citation URLs without embedded credentials become links; private source identifiers stay plain text. Links use noopener/noreferrer/nofollow. Avatars use HTTPS with no referrer. Branding colors are validated hex values with contrasting header/launcher text.

## Operations and verification

```powershell
docker compose exec -T -e LIVE_INGESTION=1 api pytest -q
docker compose exec -T api python -m app.cli check-rls
docker compose exec -T api alembic current
corepack pnpm -r --if-present lint
corepack pnpm -r --if-present typecheck
corepack pnpm -r --if-present test
corepack pnpm -r --if-present build
corepack pnpm --filter @acs/web exec playwright test
```

Use `LLM_PROVIDER=demo` for offline browser tests; it is a clearly labelled transport fixture, not a real AI model. The widget browser test starts an ephemeral plain-HTML server on port 3101 and uses the real Next.js site and API, database, ingestion worker and stream. It covers citations, safe hostile text, separate widget histories, reload restoration, mobile sizing, Escape/focus, installation copying and live preview. Tests create throwaway local accounts/content; backend tests use an isolated test database.

Public routes: `GET /widget/v1/loader.js`, `GET /widget/frame/{public_key}`, `POST /public/v1/widget/sessions`, and the existing scoped `/public/v1/chat` transport. Management routes under `/api/v1/orgs/{org}/chatbots/{bot}` include `GET /widget-config`, `POST /domains`, `POST /domains/{id}/verify`, `DELETE /domains/{id}`, and `PATCH /widget-retention`. Domain mutations require the verified member's `domain:manage` permission. Viewer access is read-only.

This phase does not establish production model quality, traffic/load capacity, a sub-50ms main-thread timing benchmark, automated DNS renewal, wildcard domains or automatic database privacy purges. Verification expires fail-closed instead of silently trusting ownership forever.
