# AUD-07 — Widget lifecycle, reliability and public response privacy

Date: 26 November 2026 (Asia/Colombo). Scope: Milestone A7 / AUD-07 and WIDGET-PRIV-01.

## 1. Decision

**AUD-07: PASS for local validation** (Linux containers, Chrome). **WIDGET-PRIV-01: PASS** (confirmed and fixed).

Final: backend **1,192 passed, 0 failed, 17 conditional skips** (the 17 proxy tests pass separately), widget 19 and web 243 unit tests, 17 of 17 browser tests, smoke, lint, types and FORCE RLS pass; performance 10 of 10 declared runs. No migration. Nothing committed or deployed. **The MVP remains NOT READY.**

| # | Acceptance criterion | Result |
|---|---|---|
| 1–2 | Same-key and concurrent initialization idempotent | PASS |
| 3 | Different keys isolated | PASS |
| 4–5 | Teardown repeatable, releases what it owns; no stale callbacks | PASS |
| 6 | SPA remounting (Next.js client navigation) | PASS |
| 7 | Resume and reset | PASS |
| 8 | Stream cancellation keeps backend accounting | PASS |
| 9 | Capability and origin checks | PASS (unchanged; existing suites) |
| 10 | Public data minimization | PASS |
| 11 | Dashboard usage and citations | PASS |
| 12 | Mobile and keyboard in tested journeys | PASS |
| 13 | Bundle budget | PASS (5,248 of 10,240 gzip bytes) |
| 14 | Regressions | PASS (one contract-driven test change, section 5) |
| 15 | Security and performance gates | PASS (local) |

## 2. Repository baseline

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`, with the uncommitted A1–A6.1 and earlier user work. Before any edit: SHA-256 inventory of 1,844 files, patch, container inventory and environment flags without values ([preflight](evidence/AUD-07/preflight/preflight.json)). A copy of the widget source and built assets was kept. Only this session changed files. Disposable stack `acs-a7-qa`: synthetic credentials, `demo` LLM, `hash` embeddings; developer services untouched; no paid call.

Baseline: backend **1,183 passed, 17 skipped** ([log](evidence/AUD-07/baseline/full-suite.log)); widget 7 unit tests; loader 9,200 bytes, 4,063 gzip as served.

Differences from the documents: the served bundle was not byte-identical to a build of the source at `HEAD` (variable naming differs between toolchains; behaviour of that difference was not otherwise assessed). It is now rebuilt from source.

## 3. Gap matrix

| Requirement | Before | Source | Evidence | Change |
|---|---|---|---|---|
| Idempotent initialization | FAIL | `loader.ts` created a frame per evaluation | [probe](evidence/WIDGET-PRIV-01/before/old-observations.json): 2 tags → 2 frames, 2 listeners, 2 bootstraps | page-wide registry (`lifecycle.ts`) |
| Duplicate install keeps working | FAIL | both frames shared one resume entry | the second rotated the first's token: first widget answered “Chat is unavailable” | one instance per identity |
| Teardown API | NOT_IMPLEMENTED | none; anonymous listener never removed | `window.AcsChat` undefined | `destroy`, owned listener and timer |
| Independent instances | PASS for different keys | separate frames | existing widget journey | explicit `data-instance-key` for same-key instances |
| Stale load after “New chat” | FAIL (code) | a bootstrap already running could save over the new session | source inspection only, not reproduced in a browser | generation check, abort |
| Stream cancellation on removal | PASS (browser + server) | frame removal ends its requests | journey 4: stored `interrupted` | none needed |
| `postMessage` checks | PASS, tightened | source, origin and nonce checked | forged messages ignored | also type-checks payload |
| Status text | FAIL | three strings ended in U+FFFD since `HEAD` | probe: “Connecting�” | real ellipsis |
| Public response data | FAIL | `/public/v1/chat` and `done` used the dashboard shape | probe and backend tests | public projection |
| Origin, key rotation, domain removal, capability | PASS | `widget_chat.py`, `widget_domains.py` | existing suites | unchanged |
| Keyboard, Escape, focus, 390 px | PASS | `panel.ts` | existing and new journeys | none |

## 4. Lifecycle design

The first loader copy creates a registry stored on `window[Symbol.for("acs.chat.v1")]`; later copies reuse it. Identity is API origin, page origin, bot key and instance key. Each instance owns one frame, one `message` listener, at most one timer, and a random per-mount nonce. Everything else (credentials, requests, streams, transcript) lives inside the frame and ends when the frame is removed, so no teardown handshake is needed except for `forget`, whose storage only the frame can reach. There is no bearer or resume token and no transcript on the host page.

Configuration conflicts: identity consists of every setting the loader accepts, so two installs cannot disagree about one instance; a different API origin or instance key is a different instance. A frame that has not spoken for 15 seconds is replaced by the next `mount`, so a failed load does not block.

Inside the frame: bootstrap and history now carry an abort signal and a generation number; “New chat” and “forget” raise it, so earlier work cannot write a session or a transcript afterwards.

## 5. Modified files

- Widget: `apps/widget/src/lifecycle.ts` (new), `loader.ts`, `panel.ts`, `scripts/check-size.mjs` (version from `package.json`), `package.json` 1.1.0; rebuilt `services/api/widget_assets/v1/`.
- API: `app/services/public_view.py` (new), `services/conversations.py` (public turns emit public events), `services/widget_chat.py` (branding allowlist), `api/widget_chat.py` (history), `api/widget_install.py` (`instance_key`).
- Tests: new `apps/widget/src/lifecycle.test.ts`, `apps/web/e2e/widget-lifecycle.spec.ts`, `tests/integration/api/mvp_improvement/test_widget_public_privacy.py`. **One existing test changed:** `test_citation_provenance.py` asserted internal `chunk_id` in the public stream; it now checks `chunk_id` on the stored citation (both surfaces) and requires the public stream to be exactly the public projection of it.
- Docs: `WIDGET_DEPLOYMENT.md`, `CHAT_ENGINE.md`, this report, tracker; tools `*_a7.py`.

## 6. Public contract

| Surface | Before | After |
|---|---|---|
| history message | id, role, content, status, citations, feedback, **input_tokens, output_tokens, estimated_cost_usd, usage_estimated, error_code, latency_ms** | id, role, content, status, feedback, citations |
| citation | id, title, uri, page, **document_id, chunk_id** | id, title, uri (plain https only) |
| `meta` | **conversation_id**, message_id | message_id |
| `error` | internal failure code, message | `answer_failed`, message |
| `done` | dashboard message shape | same as a history message |
| bootstrap | token, resume token, expiry, name, welcome, branding | unchanged fields; branding limited to its declared keys |
| feedback, satisfaction, handoff | status values | unchanged |

Dashboard responses, stored records and accounting are unchanged. Error responses remain the shared problem format; some `detail` texts are operator-oriented (for example `model_unavailable`) and were not changed (observation WIDGET-ERRORS).

Compatibility: the 1.0.0 loader reads `role`, `content`, citation `id`/`title`/`uri` and error `message`, all still present; an empty `uri` renders as plain text as private files did before. Deploy the API image, which serves both loader and frame. Custom integrations reading removed fields would break.

## 7. WIDGET-PRIV-01

**Confirmed, then fixed.** A visitor could read token counts, estimated cost, usage flags and error codes of **their own** conversation; these appear in the capture of the old widget. Document and chunk ids were also exposed: the old route returned stored citations unchanged, which hold both. That part is established from the code, because the answer in the old capture was cut off and carried no citation. No cross-tenant access was found. Sanitized captures: [before](evidence/WIDGET-PRIV-01/before/old-public-responses.txt), [after](evidence/WIDGET-PRIV-01/after/public-responses.txt). Backend tests require exact field sets for session, `meta`, `delta`, `done`, `error`, history and citations ([red](evidence/AUD-07/red/privacy-old-backend.log), [green](evidence/AUD-07/static/third.log)); journey 5 inspects real network responses and compares the dashboard.

## 8. Teardown, cancellation and sessions

| Case | Verified |
|---|---|
| Same tag twice and concurrently | one frame, one listener, one frame request |
| 25 mount/destroy cycles (real loader, stand-in frame); 30 in unit tests | no frame, listener or timer left; second destroy returns false |
| Destroy while loading / forged or late messages | no resurrection; ignored (unit and browser) |
| Host removes the frame | next mount replaces it, one listener |
| Destroy mid-answer | stored `interrupted`; no active lease or conversation lock afterwards ([check](evidence/AUD-07/browser/leases-after.log)); next question answered |
| Destroy before admission, during embedding, SSE, finalization (server side) | covered by the existing lifecycle and cleanup tests, which pass; not separately driven from a browser |
| Reload, destroy and remount | conversation resumes |
| Explicit second instance | separate conversation; destroying it leaves the first |
| `forget`, “New chat” | new conversation next time |
| Expired, revoked, rotated key, removed domain, foreign origin | existing suites pass |

A cut-off request does not mean the model provider stopped or will not bill; reserved usage stays charged.

## 9. Bundle size

| | Before (served) | After |
|---|---|---|
| Source (`src/*.ts` without tests) | 17,604 bytes | 25,207 bytes |
| Built (minified) | 9,200 bytes | 12,365 bytes |
| Gzip | 4,063 (manifest 4,053) | **5,248** |
| Budget | 10,240 gzip | unchanged |

A build of the unchanged source gave 10,094 bytes (4,317 gzip), so part of the growth over the served 9,200 bytes comes from rebuilding. No dependency added.

## 10. Browser journeys

Production web build, real API, database and Redis; widget bundle as served by the API; synthetic sites on separate origins. [7 journeys](evidence/AUD-07/browser/lifecycle-second.log) pass, and all 17 browser tests pass together ([log](evidence/AUD-07/browser/playwright-all.log)). Screenshots: [answer](evidence/AUD-07/screenshots/widget-answer.png), [390 px](evidence/AUD-07/screenshots/widget-390px.png). Checks that only concern the host page use a stand-in frame document so the public rate limits are not touched. The sign-up counters of the disposable stack were reset once between runs; limits are unchanged. Chrome only; not an accessibility certification.

## 11. Regression results

| Check | Result |
|---|---|
| Full backend suite with live ingestion | 1,192 passed, 0 failed, 17 skipped, 795 s; c100 in that run 64 successes, P95 1,517 ms ([log](evidence/AUD-07/full/backend-full.log), [JUnit](evidence/AUD-07/full/backend-full.xml)) |
| New backend widget privacy and frame tests | 9 passed |
| Widget unit tests | 19 passed (12 new) |
| Web unit tests; ESLint; type checks | 243 passed; pass; pass |
| `pnpm format:check` | **FAIL**, the same 8 files (FMT-01) |
| `ruff check`, `ruff format --check`, strict `mypy` | pass ([log](evidence/AUD-07/static/third.log)) |
| Widget and web production builds; runtime Docker build (ships the identical 1.1.0 bundle) | pass ([image](evidence/AUD-07/runtime/image-bundle.log)) |
| Runtime proxy tests | 17 passed |
| Alembic head / current; FORCE RLS | `0007` / `0007`; no unprotected tables |
| Smoke; all browser tests | pass; 17 passed |
| CI; other browsers | NOT_TESTED |

Preservation: AUD-01 18, AUD-02 32, AUD-03 159, AUD-04 197 (+17 runtime), AUD-05 100, A5.1 32, AUD-06 26, A6.1 9, auth/RBAC/isolation 89, widget 21, analytics 13, conversations 19 — no failure.

## 12. Performance preservation

Declared before running ([plan](evidence/AUD-07/perf-plan.json)); unchanged workload and gates; every run kept.

| Series | c100 successful P95 ms per run | Median / max | Successes of 100 | Failed |
|---|---|---|---|---|
| [Unloaded](evidence/AUD-07/perf/unloaded-5/summary.json) | 1,574 / 1,564 / 1,613 / 1,642 / 1,678 | 1,613 / 1,678 | 65–70 | 0 of 5 |
| [With crawling](evidence/AUD-07/perf/mixed-crawl-5/summary.json) | 1,723 / 1,755 / 1,756 / 1,730 / 1,747 | 1,747 / 1,756 | 57–63 | 0 of 5 |

Worst margin 244 ms. Crawl load: 34 crawls, 408 pages, no failure. AUD-07 does not change the dashboard send path measured here, so the faster unloaded figures than A6.1 are host variation, not an improvement. PERF-01 stays hardware-sensitive.

## 13. Failed attempts

| What failed | Cause | Fix |
|---|---|---|
| Old-widget spec, 6 of 7 not run | serial mode stops at the first failure | a separate probe recorded the rest |
| Probe, twice | my script: a syntax error; then it asserted an answer the defect prevents | recorded as an observation |
| Backend edit script stopped halfway; tests ran against half-applied code | wrong expected count in my script | applied the rest ([first](evidence/AUD-07/green/api-widget.log), [second](evidence/AUD-07/green/api-widget-2.log)) |
| Static checks twice | typing of my fake provider | corrected |
| Privacy journey | my spec reloaded mid-answer | wait for the finished answer |

## 14. Limitations, rollout and rollback

- Chrome with `localhost` origins only; storage partitioning in other browsers is not verified.
- `forget` waits up to 5 seconds for a frame that never answers, then removes it; the entry then stays.
- Deploy API (loader, frame and public shape) together; a cached 1.0.0 loader keeps working for its cache hour.
- Rollback: previous API image. No data or schema change. Rolling back restores the internal fields in public responses.

## 15. Remaining Milestone A observations, with proposed priority

All seven audit tasks now have local passing evidence. These remain; none was started here.

| Priority | ID | Evidence | Why this priority / next step |
|---|---|---|---|
| P1 before any public deployment | DEPLOY-01 | `FORWARDED_ALLOW_IPS` unset: all visitors share one rate-limit bucket (A4) | set Caddy's fixed address and verify ingress and TLS |
| P1 | CI-01 | CI runs neither the 17 proxy tests nor the browser suite (A4.1) | gates exist only on one laptop |
| P1 | AUD05-SANDBOX | parser child shares user, filesystem and network (AUD-05) | separate user/namespace and no network for the parser |
| P1 decision | MIG-02 | downgrade below 0007 refused after deletions, otherwise destructive (A4.1) | decide forward-only with restore, and rehearse a restore |
| P2 | FMT-01 | `format:check` fails on 8 files and CI runs it | mechanical; unblocks CI |
| P2 | AUD05-RECOVERY | hard-killed jobs recover after up to about 17 min; sweeper shares both slots | dedicated one-slot maintenance worker |
| P2 | OPS-BEAT / DEVBEAT-CRASH | production beat health check is wrong; developer beat crashed and has no restart | schedule-progress health check; restart policy |
| P2 | PERF-01 | passes locally; a throttled host exceeded the gate (A6.1) | measure on the target server |
| P3 | ENV-01 | developer images are stale (migrate predates 0007; worker runs old code) | rebuild developer images |
| P3 decision | AUD05-DOCX | very large `.docx` XML now fails (AUD-05) | state the limit or raise it after measurement |
| P3 | ORG-ORIGINALS | soft-deleted chatbots keep originals; organization deletion would drop outbox rows | define retention and purge |
| P3 (new) | WIDGET-ERRORS | some public error `detail` texts are operator-oriented | public error mapping |
| P3 (new) | WIDGET-BROWSERS | storage partitioning outside Chrome untested | cross-browser check before relying on resume |

Semantic citation quality (AUD-02) remains blocked without a real model, and production ingress stays unverified.
