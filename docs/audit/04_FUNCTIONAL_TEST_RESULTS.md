# Functional test results

All claims below refer to safe local fixtures or local browser accounts. The full original backend suite passed 582 tests with live ingestion enabled; frontend suites passed 213 web and seven widget tests; Playwright passed five tests. Raw JUnit, command logs and browser JSON are under `evidence/`. A green suite is not a full feature certification.

## Foundation and identity

PASS: application builds, static checks, migration/database tests, service health and FORCE RLS checks. PASS in exercised tests: registration/email verification, login/logout, password reset/reuse rejection, session expiry/revocation, organizations, membership roles, server-side authorization and manipulated-ID rejection. Password/session behavior is covered in `services/api/tests/unit` and `tests/integration/api`; exact test names are in `evidence/baseline.xml`.

The added workflow created distinct **TechMart** and **SkillHub** owners, bots, document sets and conversations in a disposable database. TechMart requests using SkillHub organization/bot/document/conversation IDs were rejected with 404. A legal search returned 200 but excluded the other organization's documents. That 200 in `business_workflow.json` is not an authorization bypass. Database RLS and vector/file-key scoping have separate existing tests.

## Dashboard and ingestion

PASS in tested paths: chatbot create/list/update/delete, persisted branding/settings, document management, retrieval playground, UI forms/loading/error components and route guards. Frontend component tests isolate API behavior; real browser tests cover integration paths rather than every possible UI state. Mobile/keyboard basics have limited browser checks; full WCAG/assistive technology testing is NOT_TESTED.

The named workflow stored ten corpus chunks per organization with min/max vector dimensions both **1536**. It additionally parsed PDF and DOCX through the real extractor/indexer and asserted nonzero database chunks, not just ready status. Existing tests exercise text cleanup/chunk bounds, invalid/corrupt/empty/oversized formats, duplicates, jobs/retries/states, website fetching/SSRF, versions and deletion. LIVE_INGESTION=1 runs the separate local Celery/S3 integration path. The named fixture itself uses an in-memory object store and deterministic worker execution; it does not claim twenty real distributed jobs.

Physical document deletion was followed by zero remaining chunks and zero stale search results. Test corpus content is fictional and isolated from production. Live embedding generation is BLOCKED without credentials/model approval.

## Chat, controls and feedback

PASS for existing fixture contracts: dashboard/public authorization, conversation/message persistence, SSE events, context-window bounds, insufficient-evidence fallback, provider timeout/retry/error paths, disconnect/cancellation, quota reservations/accounting, rate/concurrency leases and feedback validation. Provider implementations are replaced or demo responses are used for these tests. They validate plumbing, not model faithfulness or resistance to semantic injection.

FAIL: the default database pool prevents the publicized concurrency controls from providing safe admission under the staged authenticated workload (AUD-01). FAIL: a source omitted by context rendering is still accepted by citation validation (AUD-02). FAIL: production embedding settings permit HTTP (AUD-03). These regressions are intentionally left failing in dedicated audit test directories; no application fix was made.

## Business workflow evidence, steps 1–17

1. Register owner and verify identity: added `api.signup` fixture plus original identity tests; separate real browser registration uses Mailpit.
2. Create organization: TechMart/SkillHub IDs are distinct in the isolated database.
3. Create chatbot: real API creates one per owner; browser creates two for embed tests.
4. Upload knowledge: twenty text corpus docs plus PDF and DOCX through API/indexing helpers.
5. Processing: real parser pipeline is driven to ready in the controlled fixture; separate LIVE_INGESTION test exercises queued worker/storage integration.
6. Stored records: database count and 1536-dimension assertions recorded in `business_workflow.json`.
7. Ask questions: 100 retrieval API calls plus authenticated demo chat.
8. Answer/citation validation: demo transport/source rendering verified; **real answer correctness and semantic attribution BLOCKED**, and AUD-02 fails.
9. Branding: color #13579B persisted and re-read.
10. Embed: API frame/config verified; browser copies installation script with real public key.
11. External local website: browser HTTP server on localhost:3101 loads the widget from localhost:8000.
12. Widget questions: SSE demo response/source display on plain HTML and initialization on Next.js passed.
13. Persistence: saved dashboard message assertion plus browser widget reload/resume passed.
14. Second organization: SkillHub has separate owner, bot, docs and conversation.
15. Isolation: manipulated ID and search exclusions, RLS tests and browser multi-bot check passed.
16. Delete document: real delete operation in the fixture.
17. No stale knowledge: direct chunk count and subsequent retrieval exclusion both asserted.

The named API test and browser test use different isolated identities. They supply complementary evidence; the entire journey is **PARTIALLY_IMPLEMENTED / BLOCKED at live AI validation**, not a single fully verified production scenario.

## Test accounting

Original suites: 807/807 PASS. Four distinct added audit functions: one final PASS, three final FAIL. Final distinct total: **811**, with **808 passed and 3 failed**. Across repeated runs: 814 invocations, 809 passes and five failures. The initial audit workflow failure was incorrect audit DOCX fixture construction, corrected without touching the parser. An initial performance collector PASS meant measurements were recorded; the later acceptance assertion fails. The 100 RAG rows are evaluation cases, not 100 extra pytest tests. See `test_results.json` and report 12 for commands and exit codes.
