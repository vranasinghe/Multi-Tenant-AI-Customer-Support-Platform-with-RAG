# Phase 6 — Website widget v1.1.0

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

## Lifecycle (1.1.0)

One widget exists per API origin, bot key and instance key. Including the snippet twice, or
mounting again, keeps the existing one. Different bot keys are independent. To show the **same**
chatbot twice on purpose, give the second tag `data-instance-key="footer"` (1–32 of
`A–Z a–z 0–9 _ -`); each instance key keeps its own conversation.

```js
window.AcsChat.mount({ botKey: "pk_live_…" });                 // returns {botKey, instanceKey, destroy}
window.AcsChat.get({ botKey: "pk_live_…" });
window.AcsChat.destroy({ botKey: "pk_live_…" });               // safe to repeat
window.AcsChat.destroy({ botKey: "pk_live_…", forget: true }); // also forget the visitor here
```

`mount`, `get` and `destroy` accept `instanceKey` and `apiOrigin` (default: the origin the first
loader came from). The API exposes no credential or transcript to the host page.

`destroy` removes the frame and its one `message` listener; removing the frame ends its bootstrap,
history and streaming requests, and the server stores a cut-off answer as `interrupted` with its
reserved usage kept (the model provider may still bill it). The visitor's resume entry stays, so
a later mount continues the conversation. `forget: true` asks the frame to delete that entry
first; nothing is deleted on the server. **New chat** inside the widget does the same and starts
over. In a single-page app, call `destroy` in the unmount/cleanup of the component that mounted
it. A frame that never loads is replaced by the next `mount` after 15 seconds.

**What `forget` does not guarantee.** The page only asks. If the frame confirms, the entry was
deleted (a browser that refuses storage access has none to delete, and the frame still confirms).
If no confirmation arrives within 5 seconds, because the frame never loaded, is blocked or is
busy, the widget is removed anyway and **the resume entry may remain**, so a later mount can
continue the earlier conversation. `destroy` returns `true` as soon as removal is under way and
does not report which happened. Do not rely on `forget` to protect a shared computer; **New
chat** inside a loaded widget deletes the entry directly.

Resume uses the frame origin's `localStorage`. Browsers that block or partition third-party
storage keep a conversation only while the page is open; this was tested in Chrome with
`localhost` origins, not across browsers.

## What the visitor receives

`GET /public/v1/chat` and the streamed events carry, per message: `id`, `role`, `content`,
`status`, `feedback` and `citations` of `{id, title, uri}`, where `uri` is set only for a plain
`https` link. `meta` is `{message_id}` and a failed answer is
`{code: "answer_failed", message}`. Token counts, cost, latency, internal error codes and
document or chunk ids are not sent. The dashboard transcript keeps all of them.

## Upgrading from 1.0.0

Deploy the API image (it serves the loader and the frame): both change together. A loader cached
for up to an hour still works with the new API, which sends every field 1.0.0 reads; it simply
lacks the lifecycle API. A new loader against an old API ignores instance keys in the frame, so
roll the API first. Custom integrations that read removed fields must change.

## Distribution and rollout

```powershell
corepack pnpm --filter @acs/widget build
docker compose up -d --build --wait
```

The build writes `apps/widget/dist/loader.js` and copies its deployable distribution to `services/api/widget_assets/v1/loader.js`, with `manifest.json` identifying semantic version **1.1.0** and its measured gzip size. The bundle is dependency-free, approximately **5.2 KB gzipped** (under the enforced 10KB budget), and includes both the host loader and isolated iframe UI. The API exposes `/widget/v1/loader.js` with JavaScript MIME type, nosniff and a one-hour cache. The `v1` path permits compatible updates; keep previous artifacts/images for rollback rather than marking this URL immutable.

Build the widget **before** building the production API image. Its runtime Docker stage includes `widget_assets`. Apply migration **0006** before deploying the new API. It adds a FORCE-RLS-protected `chatbot_domains` table, retention settings and hashed resume credentials. Existing Phase 5 sessions remain compatible. Downgrading drops origin/resumption settings and must be treated as destructive; prefer a forward fix.

Serve everything through HTTPS. Preserve the frame route's per-origin `frame-ancestors` CSP; do not replace it with a wildcard or global DENY header. Do not cache frame or session responses. Disable proxy buffering for SSE and permit the configured chat timeout. Set `FORWARDED_ALLOW_IPS` to the proxy's exact address before relying on IP limits: no peer is trusted by default, so until then all visitors share the proxy's address (DEVELOPMENT.md section 10, DEPLOY_CONTABO.md "Trusted ingress"). The proxy must replace client-supplied `X-Forwarded-*` headers and be the only path to the API. Tenant quotas and session limits also apply independently of IP controls.

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
