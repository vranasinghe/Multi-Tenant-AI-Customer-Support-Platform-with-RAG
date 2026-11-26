# AUD-06 — Conversation inbox: gap audit, corrections and validation

Date: 26 November 2026 (Asia/Colombo). Scope: Milestone A6 / AUD-06, section 11 of the approved plan.

## 1. Executive summary

**AUD-06: functionally complete; not marked PASS, because one preserved performance gate was not met cleanly.**

- The original finding is obsolete: Phase 7 had already built a real inbox. This task closed the gaps that remained (section 5).
- Acceptance criteria 1–14 are met with observed evidence.
- Criterion 15 is **not** met: the strict chat capacity gate (success P95 ≤ 2,000 ms at concurrency 100) failed in the full suite at 2,110 ms. An alternating A/B series shows the same failure rate with and without AUD-06's backend changes (1 of 5 each), so it is the open PERF-01 margin on this host, not an effect of this work. No threshold was changed and nothing was rerun to obtain a pass.

Final full backend run: **1,173 passed, 1 failed (that gate), 17 conditional skips**. Web 243 and widget 7 unit tests, ESLint, type check, browser 10/10, smoke, runtime proxy 17/17 and FORCE RLS pass. Nothing was committed or deployed. **The MVP remains NOT READY.**

## 2. Repository baseline

HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`, with the uncommitted A1–A5.1 and earlier user work. Before any edit: SHA-256 inventory of 1,434 files, patch of uncommitted changes, container inventory and environment flags without values ([preflight](evidence/AUD-06/preflight/preflight.json), [hashes](evidence/AUD-06/preflight/before_hashes.json)). No other session was running in this folder. No commit, push, reset, clean or history change.

**Environment:** a disposable Compose project (`acs-a6-qa`): synthetic credentials, `demo` LLM, `hash` embeddings, empty provider keys, its own PostgreSQL, Redis and object storage, images built from the current tree (migrations `0001`–`0007`). The developer stack's worker and beat were not restarted.

**Baseline** before changes: backend **1,148 passed, 0 failed, 17 skipped** ([log](evidence/AUD-06/baseline/full-suite.log)); web 220 and widget 7 unit tests, ESLint and type check pass; `format:check` fails on 8 files (FMT-01) ([log](evidence/AUD-06/baseline/web-checks.log)).

## 3. Comparison with the historical finding

AUD-06 described an unconditional “No conversations yet” placeholder with disabled filters, and no organization-wide listing. **Neither exists any more.** Phase 7 added `GET /orgs/{org}/conversations` (search, filters, cursor pagination), a transcript endpoint, the inbox and conversation screens, RBAC, RLS (migration `0007`) and conversation actions. The remaining work was gap closure, not a new inbox.

## 4. Phase 7 functionality already present

Organization inbox with chatbot, channel, status, date, feedback, satisfaction, unanswered, grounding and text filters; transcript with citations and feedback; resolve/reopen, CSAT, handoff, unanswered marking, delete with usage retention, CSV export, retention and analytics. All preserved.

## 5. Gap matrix

“Before” is the state at the start of this task; “After” is what was verified.

| # | Requirement | Before | Evidence for “before” | Change | After |
|---|---|---|---|---|---|
| 1 | Organization-scoped list | PASS | `services/inbox.py`; existing tests | none | PASS |
| 2 | Real widget conversations | PASS | code; runtime test | none | PASS |
| 3 | Real playground conversations | PASS | code; runtime test | none | PASS |
| 4 | Chatbot filtering | PASS | existing API and select | none | PASS |
| 5 | Channel filtering | PASS | existing | none | PASS |
| 6 | Conversation pagination | PARTIALLY_IMPLEMENTED | UI replaced the list on “Load more”; a bad cursor silently returned page 1 | accumulate pages; strict scoped cursors | PASS |
| 7 | Transcript pagination | FAIL | newest 200 only, silently | new messages endpoint, `older_cursor`, “Load earlier messages” | PASS |
| 8 | Timestamps | PARTIALLY_IMPLEMENTED | list showed last activity only; messages carried none | message `created_at`; both shown | PASS |
| 9 | Message status | PASS | shown as stored | none | PASS |
| 10 | Stored citations | PASS | snapshots rendered as text | page number shown; list labelled | PASS |
| 11 | Conversation status | PASS | Phase 7 | none | PASS |
| 12 | Search and date filters | PARTIALLY_IMPLEMENTED | “From” was parsed as midnight UTC, “To” as local | both local | PASS |
| 13 | Usage and analytics integration | PASS | existing tests | none | PASS |
| 14 | Loading states | PASS | skeletons | none | PASS |
| 15 | Empty states | PARTIALLY_IMPLEMENTED | filtered result said “No conversations yet” | “No matching conversations” with clear action | PASS |
| 16 | Error and retry | PARTIALLY_IMPLEMENTED | first load only; an error stayed over a new filter until success | per-scope state; page retry keeps content | PASS |
| 17 | Role-based access | PASS | `policy.py`, `require(...)` | none | PASS |
| 18 | Organization switching | PARTIALLY_IMPLEMENTED | the app remounts per organization; the components themselves kept earlier data across filter and prop changes (`useAsyncData`) | scope-keyed components | PASS |
| 19 | Mobile layout | FAIL for long unbroken text | 390 px overflow, found by the new browser journey | `wrap-anywhere` | PASS (selected checks) |
| 20 | Keyboard access | PASS | links and native controls | none | PASS (selected checks) |

Runtime evidence for the “before” states: [13 failing frontend tests](evidence/AUD-06/red/web-unchanged-code-names.log), [21 of 26 backend tests failing](evidence/AUD-06/red/api-unchanged-code.log), [first browser run](evidence/AUD-06/browser/inbox-first.log).

## 6. Reused and 7. changed

**Reused:** the inbox and transcript endpoints, permissions, RLS, `get_detail`, `message_out`, citation snapshots, UI components, `useAsyncData`, API client, existing indexes.

**Corrected or added:**
- Cursors: strict decoding (length, base64, timestamp with zone, UUID), bound to organization, list, filters and direction; otherwise `400 invalid_cursor`.
- `GET /orgs/{org}/conversations/{id}/messages?cursor&limit` (≤100) for earlier messages.
- Transcript response gains `older_cursor`; its messages gain `created_at`.
- Inbox screen: remounted per organization and per filter combination; pages accumulate.
- Transcript screen: remounted per organization and conversation; earlier pages; times; sources list.

## 8. Architecture before and after

```
before  list ──cursor (unchecked)──► replaces the rows        transcript ──► newest 200, silently cut
after   list ──scoped cursor──► appends rows                  transcript ──► newest 200 + older_cursor
        state keyed by organization + filters                              └► /messages?cursor ──► earlier pages
```

## 9. API contract changes

Additive: the messages endpoint, `older_cursor`, `created_at` on dashboard transcript messages. **Behaviour changes:** an invalid or mismatched `cursor` is now `400 invalid_cursor` instead of being ignored, and cursors issued before this change are refused once. The playground transcript response still returns the newest 200 messages. The public widget history is unchanged.

## 10. Modified files

Application: `services/api/app/services/inbox.py`, `app/api/conversations.py`; `apps/web/src/components/conversations/conversations-screen.tsx`, `conversation-detail.tsx`, `src/lib/api/index.ts`, `types.ts`.
Tests: new `tests/integration/api/mvp_improvement/test_conversation_inbox.py`, `conversations-inbox.test.tsx`, `conversation-detail.test.tsx`, `e2e/conversation-inbox.spec.ts`. No existing test was changed.
Documentation and tools: this report, the tracker, `CHAT_ENGINE.md`, `API_SPEC.md`, `tools/*_a6.py`.

## 11. Migration decision

**None.** The plan proposed creation-order indexes; Phase 7 already sorts by latest activity with `ix_conversations_inbox (org_id, last_message_at DESC, id DESC)`, which is the existing validated contract and is labelled as such in the UI. Message paging uses `ix_messages_conversation`. Alembic head stays `0007`.

## 12. Roles

| Permission | Owner | Admin | Agent | Viewer |
|---|---|---|---|---|
| `conversation:read` (list, transcript, messages) | yes | yes | yes | yes |
| `conversation:write` (outcome, CSAT, handoff) | yes | yes | yes | no |
| `conversation:delete`, `conversation:export` | yes | yes | no | no |

No permission was added or widened. Verified: unauthenticated 401, non-member or removed member 404, missing permission 403, role change effective on the next request, revoked session 401, restricted organization readable but not writable.

## 13. Tenant isolation

Another organization's identifiers give 404 for the list, transcript and messages; a foreign chatbot filter returns nothing; a cursor from another organization is refused and a forged one only moves within the caller's own rows; widget capability tokens get 401 on all three routes. Every query keeps its `org_id` predicate under FORCE RLS with the unprivileged role. A cursor is unsigned and is **not** an authorization credential; the draft signed-cursor design is not claimed. Citations remain stored snapshots after their document is deleted, as text with no link or download.

## 14. Stale-response handling

State is discarded by remounting, not by waiting for the next answer: the previous rows, chatbot options, filters, pages, errors and transcript are gone in the same render, and late answers have nowhere to land. Covered by delayed-response component tests (organization, filter, conversation, pagination, error, unmount) and a browser journey that holds the second organization's response back. Sign-out leaves nothing visible, including after “back”. No client-side cache of conversation data exists.

## 15. Query performance

Fixture: 10,000 conversations (7,000 / 2,000 / 1,000 over three tenants), 61,994 messages including one 2,000-message transcript; 20 warmed reads each, in-process client in the QA API container, 32 logical CPUs, PostgreSQL 18.7. Target: P95 ≤ 300 ms. [Results](evidence/AUD-06/perf/inbox-data/inbox-perf.json), [plans as the runtime role](evidence/AUD-06/perf/inbox-data/inbox-plans.txt).

| Read | P95 ms | Statements | Payload bytes |
|---|---|---|---|
| list, 25 / 100 rows | 17.0 / 16.6 | 8 | 9,344 / 36,922 |
| list after 2,100 rows | 17.7 | 8 | 37,140 |
| one chatbot / widget / resolved | 13.8 / 14.9 / 13.1 | 8 | ~9,400 |
| message search | 132.7 | 8 | 9,344 |
| transcript, newest 200 of 2,000 | 17.5 (max 92.6) | 10 | 113,520 |
| older page of 50 | 13.5 | 8 | 28,651 |

Statement counts include authentication and tenant setup and do not grow with the rows returned (tested). Page reads use `ix_conversations_inbox`, `ix_conversations_status` and `ix_messages_conversation`. The `total` count scans the tenant's rows (about 4 ms here), and message search scans `messages` (about 60 ms here) although a trigram index exists; both grow with data. This is a local fixture, not a capacity guarantee.

## 16. Browser evidence

Production Next.js build (`node apps/web/server.js`) against the QA API and worker. Four journeys: widget conversation to inbox with sources and reload; playground and chatbot filtering; keyboard and 390 px; two organizations, foreign identifiers, an outsider and sign-out. Screenshots (synthetic data): [list](evidence/AUD-06/screenshots/inbox-list-desktop.png), [transcript](evidence/AUD-06/screenshots/transcript-desktop.png), [list 390 px](evidence/AUD-06/screenshots/inbox-list-390px.png), [transcript 390 px](evidence/AUD-06/screenshots/transcript-390px.png). These are selected checks, not an accessibility certification.

## 17. Regression results

| Check | Result |
|---|---|
| Full backend suite with live ingestion | **FAIL**: 1,173 passed, 1 failed (`test_strict_capacity[100]`, 2,109.8 ms), 17 skipped ([log](evidence/AUD-06/full/backend-full.log), [JUnit](evidence/AUD-06/full/backend-full.xml), [groups](evidence/AUD-06/full/groups.log)) |
| Baseline before changes | 1,148 passed, 0 failed, 17 skipped; the 26 new inbox tests account for the difference |
| New inbox backend tests | 26 passed |
| Conversation, widget, route-permission, tenant-isolation tests, focused | 72 passed with the inbox tests ([log](evidence/AUD-06/green/api-second.log)) |
| Runtime proxy tests, image `acs-api:mvp-a6-local` | 17 passed |
| `ruff check`, `ruff format --check`, strict `mypy` | pass ([log](evidence/AUD-06/static/third.log)) |
| Alembic head / current; FORCE RLS | `0007` / `0007`; no unprotected tables |
| Runtime Docker build; production web build | pass |
| Web / widget unit tests; ESLint; type check | 243 / 7 passed; pass; pass ([log](evidence/AUD-06/web/checks.log)) |
| `pnpm format:check` | **FAIL**, the same 8 files as before (FMT-01); all AUD-06 files pass |
| Smoke; Playwright, all specs | pass; 10 of 10 ([log](evidence/AUD-06/browser/playwright-all-2.log)) |
| Inbox query fixture | pass (section 15) |
| CI; native Windows backend run | **NOT_TESTED** |

By preservation group: every group passes except AUD-01 (17 passed, 1 failed: the capacity case). AUD-02, AUD-03, AUD-04, A4.1, AUD-05, A5.1, authentication, RBAC, tenant isolation, widget, analytics and conversations have no failure.

### Capacity

The series was declared after the failure and before running ([plan](evidence/AUD-06/perf-plan.json)): five pairs, alternating the AUD-06 backend files with their original versions, unchanged test and gates, every run kept ([summary](evidence/AUD-06/perf/capacity-ab-5/summary.json)). The working files were restored and hash-checked.

| Variant | c100 successful P95 ms | Median | Over 2,000 ms |
|---|---|---|---|
| with AUD-06 | 1,751 / 1,785 / 1,819 / 1,921 / 2,020 | 1,819 | 1 of 5 |
| original files | 1,766 / 1,770 / 1,805 / 1,858 / 2,036 | 1,805 | 1 of 5 |

Rejection P95 stayed under 3,000 ms and the success floors held in every run. Earlier checkpoints recorded medians near 1,600–1,700 ms on this host; why it is slower now was not established. A planned multi-run capacity series with mixed load was not run.

## 18. Failed attempts

All logs are kept under `evidence/AUD-06/`.

| What failed | Cause | Fix |
|---|---|---|
| Backend tests, 4 of 57 after the change | my message fixture reused ids across tests | unique id prefix per call ([first](evidence/AUD-06/green/api-first.log), [second](evidence/AUD-06/green/api-second.log)) |
| Static checks twice | formatting and an f-string SQL lint in my test | test rewritten ([logs](evidence/AUD-06/static/)) |
| 390 px journey | real overflow in the product | `wrap-anywhere` |
| Full browser run, 10 failures | sign-up limit of 10 per hour per IP; my first spec added five accounts | one account per spec file; QA counters reset ([log](evidence/AUD-06/browser/playwright-all.log)) |

## 19. Remaining risks and limitations

- Pages are not a snapshot. A conversation that receives a message while you browse moves to the top: it can be missed until refresh, and is never listed twice.
- The date filters use the viewer's local time zone.
- A filter keystroke reloads the list (no debounce).
- `total` and search cost grows with data (section 15).
- “Mark latest question unanswered”, handoff contact visibility to viewers and other Phase 7 behaviour were not reassessed.
- **Observation, not changed:** the public widget history (`GET /public/v1/chat`) uses the same message shape as the dashboard, including token counts, estimated cost, and citation document and chunk ids, so website visitors receive them. This predates AUD-06 (found by reading the code) and needs its own decision.
- A full run of the browser suite uses most of the hourly sign-up allowance; repeated runs on one stack hit it.

## 20. Rollback

No schema or data change. Reverting removes the new endpoint and fields; the web build and API should be deployed together, because the new screen expects `older_cursor` and `created_at`.

## 21. Decision

| Acceptance criterion | Result |
|---|---|
| 1–3 real persisted conversations; widget, playground, chatbot filter | PASS |
| 4–5 conversation and transcript pagination complete and bounded | PASS |
| 6–7 no cross-tenant access observed; roles correct | PASS |
| 8–9 old tenant data cleared at once; stale responses cannot repopulate | PASS |
| 10–12 citations safe; loading, empty, error states; Phase 7 preserved | PASS |
| 13 inbox query target | PASS (local fixture) |
| 14 new and relevant tests | PASS |
| 15 previous security and performance gates preserved | Security PASS. **Performance FAIL**: PERF-01 gate intermittently exceeded, equally without this change |

**AUD-06 is not marked PASS.** The inbox work itself is complete and validated; the remaining item is the capacity gate, which needs either a PERF-01 investigation or an explicit decision to accept AUD-06 despite it.

AUD-07, advanced conversation features, analytics work, MIG-02, CI-01, FMT-01 and Milestones B–J were not started. Nothing was committed, pushed or deployed, no production system was touched and no paid provider call was made.
