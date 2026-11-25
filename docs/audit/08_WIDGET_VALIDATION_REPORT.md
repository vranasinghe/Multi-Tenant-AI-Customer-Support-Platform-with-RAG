# Widget validation

Overall: PARTIALLY_IMPLEMENTED for release readiness. Local embed and transport integration PASS; real AI quality is BLOCKED and shared citation/concurrency defects remain. Primary evidence: `evidence/browser.log`, `baseline.xml`, `frontend_tests.log`, `widget-mobile.png`, `widget-dashboard.png`. Existing browser test source is `apps/web/e2e/widget.spec.ts`.

## Browser runtime evidence

The Playwright suite passed five tests in 12.3 seconds. The widget-specific test hosts a separate plain HTML fixture at **http://localhost:3101**, with the API at **http://localhost:8000** and Next.js at **http://localhost:3000**. It creates real local accounts/bots, waits for a document to become ready, configures local allowed origins and dynamically installs `/widget/v1/loader.js` using the public bot key.

PASS in the exercised browser flow: script initialization, launcher/open/close, message send, streamed demo output, source filename display, different-bot conversation separation, reload/resume, literal malicious welcome text, Escape focus return, 390x844 mobile frame bounds, initialization on a Next.js page, copyable install script and dashboard live iframe preview. Browser checks establish source display, not semantic citation correctness. Hostile `<img onerror>` content appears as text and the tested execution flag stays false.

The two distinct bot keys do not share the first bot's question. After changing the parent origin from the HTML fixture to Next.js, that conversation is not exposed there. This is a targeted instance/origin isolation test, not all possible session races. The existing test does not explicitly inventory every browser-console message; comprehensive console/network-outage coverage is NOT_TESTED.

## Backend and unit evidence

Passing API/unit tests cover scoped public tokens, invalid identifiers and token reuse/expiry constraints, inactive/deleted chatbot denial, preview restrictions, public/admin permission boundaries, allowed-origin/CORS checks, domain verification state, tenant isolation, rate/usage limits and session retention access. Provider failure, cancellation and SSE contract paths are fixture-tested. See actual test names in `baseline.xml`; frontend component tests use mocks where appropriate.

Public identifiers are lookup values; server-side policy and scoped tokens enforce capabilities. Secrets are held server-side and no provider key is placed in the loader/panel configuration. The iframe isolates CSS and restricts framing by configured parent origins; display uses safe DOM text/React rendering. Origin/Referer are not strong authentication. Domain verification is defense in depth, not proof of the caller's identity. Production DNS verification uses a manual flow and expires after seven days; automated tests use mocked DNS or the local-only origin allowance, not a real DNS-control proof.

## Distribution and deployment

Version and size are in `services/api/widget_assets/v1/manifest.json`, produced by `apps/widget` build. The loader is **4,053 gzip bytes**. Full frontend recursive build and API runtime image build passed, including widget packaging. `docs/WIDGET_DEPLOYMENT.md` documents install attributes, origins, DNS, retention and build/deploy ordering. A public CDN, real TLS/domain deployment, customer CSP permutations and cache invalidation were not exercised.

## Remaining gaps

- AUD-07: executing the same loader/key repeatedly unconditionally creates more iframe/listener instances; no idempotent initialization or teardown is present. This is a static finding; different-bot isolation PASS does not test repeated same-key execution.
- AUD-02: source display can present a citation for selected evidence omitted from the model prompt.
- AUD-01: backend resource starvation can interrupt widget/dashboard availability under shared load; the measured saturation route used authenticated dashboard chat, so identical widget-load rates are not asserted.
- Broad network failure/recovery, real provider errors through browser transport, mobile assistive technology, console error collection and production DNS/ingress controls remain NOT_TESTED or BLOCKED.
- Retention expiry prevents anonymous resume; a verified physical purge of old database messages is absent. Do not promise data erasure from access expiry alone.

The widget works on the tested plain HTML and Next.js hosts using the local demo provider. These results do not satisfy the live factual AI or production-security release gates.
