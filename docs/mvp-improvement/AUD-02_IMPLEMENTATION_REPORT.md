# AUD-02 implementation report — exact rendered citation provenance

Date: 22 November 2026 (Asia/Colombo). Scope: Milestone A2 / AUD-02 only.

## Decision

**PASS for deterministic citation provenance in the exercised local fixtures.** The original AUD-02 regression passes. All **32 new deterministic tests** pass (22 unit, 10 integration); the focused run including the original regression has **33 passes**. Existing RAG/conversation/authorization/widget and AUD-01 tests have **287 passes**. The full backend run has **635 passes, one failure, zero errors and zero skips (636 tests)**. Its sole failure is the unchanged **AUD-03 production HTTP embedding transport regression**. All **18 unchanged AUD-01 tests** pass in both the selected and full runs. All **five existing browser tests** pass. Backend Ruff, formatting and strict mypy pass; the local runtime image builds and FORCE RLS verification passes.

This is not a full-suite-green or release-readiness decision. Semantic citation accuracy, faithfulness, real-model prompt-injection resistance and answer quality remain **BLOCKED / not evaluated**. No live paid model was configured or invoked. Demo/scripted responses establish plumbing and provenance only. Milestone A and the overall MVP remain incomplete / NOT READY.

## Inputs and baseline

Read the MVP improvement plan, Section 7 (A2) of the implementation plan, AUD-01 implementation report and progress tracker, security audit, RAG evaluation report and prioritized fix plan. Inspected `services/api/app/rag/retrieval.py`, `services/api/app/services/chat_prompt.py` and `services/api/app/services/conversations.py`, their callers, persistence/SSE contracts and existing tests. No applicable root or ancestor `AGENTS.md` was found; the frontend-specific instructions do not require frontend changes for this backend fix.

Before application edits, captured hashes of **334 existing files** and ran the unchanged test:

```powershell
Get-Content docs/audit/tools/environment.py | docker compose exec -T api python -
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py::test_citations_must_only_reference_sources_actually_rendered -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-02-baseline.xml
```

The captured command stops if the settings check fails. Actual baseline: **one failure**, pytest 0.55 seconds, command exit 1 / wall 5.856 seconds. The assertion was `Citation accepted for selected passage omitted by escaped context budget`. Settings were local, demo LLM, hash embeddings, both provider-key-presence flags false. See [baseline log](evidence/AUD-02/baseline.log), [command metadata](evidence/AUD-02/baseline.json) and [JUnit](evidence/AUD-02/baseline.xml).

The regression uses fictional evidence: a first source containing 2,500 ampersands and a second source with a unique fact. HTML escaping expands the first body beyond the renderer's ceiling. The old prompt assembly returned a larger selected-chunk list than the actual rendered evidence, so `[2]` could resolve to unseen source metadata. Metadata/delimiter overhead and raw-character versus escaped-size accounting made the mismatch broader than this one example. Whole-prompt budgeting did not repair the citation allowlist.

## Exact modified and new files

Existing application files modified:

- `services/api/app/rag/retrieval.py`: immutable rendered context/source snapshots, one escaped UTF-8 renderer, canonical authorization of candidate IDs immediately before rendering, compatibility wrappers for existing prompt callers.
- `services/api/app/services/chat_prompt.py`: budget the actual rendered input, return the exact immutable evidence tuple, resolve citations only from that tuple, bounded incremental marker parser.
- `services/api/app/services/conversations.py`: carry rendered evidence through `Turn`, use it for fallback/stream filtering/final citation snapshots, canonicalize candidates in the existing short setup transaction, persist valid partial-output citations on failure/disconnect.

New tests:

- `services/api/tests/unit/mvp_improvement/test_rendered_evidence.py` — 22 cases.
- `services/api/tests/integration/api/mvp_improvement/test_citation_provenance.py` — 10 cases.

Documentation/tooling:

- New `docs/mvp-improvement/AUD-02_IMPLEMENTATION_REPORT.md` (this report).
- Updated `docs/mvp-improvement/02_PROGRESS_TRACKER.md`.
- New `docs/mvp-improvement/tools/capture_a2.py` and `docs/mvp-improvement/tools/verify_a2.py` for isolated capture, preservation checks and evidence inventory.
- New artifacts exclusively under `docs/mvp-improvement/evidence/AUD-02/`; [results](evidence/AUD-02/results.json) and [artifact validation](evidence/AUD-02/artifact-validation.json) enumerate results and hashes.

No existing test was edited or weakened. No migration, dependency, frontend/widget bundle, API schema, provider transport, pool/admission configuration or original audit file was changed. Hash comparison confirms the only pre-existing application files changed since the A2 baseline are the three listed above. This workspace has no `.git`; the bounded before/after inventory supplies preservation evidence, not a claim about repository history.

## Rendering and budgeting contract

`render_evidence` returns a frozen `RenderedContext` and a tuple of frozen `RenderedSource` snapshots. Each snapshot contains scalar IDs, canonical cleaned title/URI, the exact included raw excerpt and its exact escaped markup. Mutable candidate objects, heading lists and retrieval metadata do not survive this boundary. `assemble` returns the final message list and that exact tuple. The final provider user message contains those snapshot fragments verbatim; downstream citation handling does not render the source list again or re-fetch model-supplied IDs.

The context ceiling is **12,000 escaped UTF-8 bytes**, including opening/closing wrappers, source tags, escaped title/URI, body and all newlines. Overall input uses the existing conservative `token_bound`: actual UTF-8 content bytes plus 32 per message and 32 framing allowance. This is a byte-based token bound, not an exact tokenizer measurement. The configured input/model-window/output allowances remain enforced.

Assembly first drops oldest complete history pairs if the full input is too large, then reduces the evidence byte allowance using the actual system/preferences/question/framing cost. If those fixed costs cannot fit even an empty context, it raises the existing pre-stream `context_limit` error. Sources retain ranked order. Empty bodies and metadata that cannot fit with any body are skipped. The first partially included body ends selection. Prefix selection happens on Unicode codepoints before HTML escaping, so neither UTF-8 codepoints nor HTML entities/tags are cut. Citation IDs are contiguous and assigned only after inclusion is determined; IDs remain fixed throughout this model invocation. They are message-local, not global document identifiers.

The legacy `render_context(max_chars=...)` signature remains for existing callers, but the parameter now consistently means escaped UTF-8 bytes including markup. There is no second character-count budget. The trusted guard and tenant preferences remain in the system role; escaped document evidence and question remain in the user data block.

## Authorization and lifecycle boundary

Immediately before rendering, `authorize_chunks` queries canonical rows by candidate chunk IDs using the existing tenant-context session and FORCE RLS. Explicit predicates require the exact org and chatbot, a nondeleted chatbot, matching document chatbot, a positive published document version, equal chunk/published versions and the current embedding model. Missing/deleted, superseded, retired-model, foreign-tenant and foreign-chatbot candidates are discarded. Metadata and body are reloaded from authorized rows, preventing a candidate with a valid chunk ID but forged title, URI or document ID from supplying citation data. Duplicate IDs are deduplicated in ranked order. Failed reindexing retains the last valid published version, as before.

This check occurs in A1's existing bounded setup transaction after fresh dashboard/widget authorization and embedding, before prompt construction/reservation/commit. It adds one bounded query, not another concurrent session, long-lived lock or checkout. Embedding and provider work still run without a database connection. Pool sizes, auth/setup/org gates, timeout/watchdog handling, cancellation shielding and conservative usage accounting are unchanged. There is no database read per streamed marker.

Authorization is a **point-in-time prompt-construction check**. A later document update/deletion cannot retract evidence already sent to an in-flight provider. Existing historical citation snapshots remain historical metadata rather than being rewritten. This change does not implement live document revocation, physical retention/purge or a new download entitlement.

## Streaming and persistence

`CitationStream` processes characters incrementally, independent of provider delta boundaries. Only canonical ASCII numeric markers `[1]` through `[999999]` can be citation references, and only IDs in the actual rendered tuple are allowed. Zero, leading-zero, unknown/omitted, signed, spaced, decimal/list, Unicode-digit, mixed, nested and overlong numeric markers cannot resolve. Short nonnumeric brackets such as `[note]` remain ordinary text. Incomplete and overlong/nested groups are discarded. Pending marker text is bounded to 64 characters; existing output/time limits also remain active.

A marker is withheld until it is complete and validated, so an unknown reference cannot already have escaped in an earlier SSE delta. Repeated valid markers stay in answer text but produce one citation snapshot per included source, in rendered-source order. The count-only helper form remains for existing pure-helper compatibility tests; the live service always passes the actual rendered evidence tuple. `citations_for` accepts that tuple, not a candidate list or a provider-supplied metadata object.

Terminal citations are derived from exactly the sanitized content emitted to the client and the same evidence tuple. Completed, failed and interrupted partial answers persist corresponding valid source snapshots. The existing `show_sources` setting remains respected. Incomplete pending text is not flushed at EOF/cancellation. Empty rendered evidence uses the configured fallback without a provider call; unsupported numeric markers in that fallback are also stripped.

The existing `meta`, `delta`, `error`, `done` names and fields, citation fields (`id`, `document_id`, `chunk_id`, `title`, `uri`, `page`), feedback, usage/persistence schema and widget/dashboard rendering contracts are preserved. Citation snapshots contain existing public response metadata, not evidence excerpts, prompt text, scores, ranks or internal authorization diagnostics. No sensitive prompt/content logging was added.

## Security and regression validation

The new unit tests verify ampersand expansion, all HTML special characters, escaped metadata, Sinhala/Chinese/emoji UTF-8, byte caps and balanced parseable markup, immutable excerpts, metadata omission before ID allocation, history/fixed-input budgeting, partial-source exclusion, empty evidence, repeated citations and bounded invalid/incomplete markers. Invalid-marker cases run across **every two-delta split position**, plus one-character deltas.

The new real-PostgreSQL/RLS/Redis integration fixtures use fictional documents and a scripted in-memory provider. They capture provider input only in test memory. Tests compare rendered source IDs, SSE delta concatenation, terminal content/citations and persisted transcripts; exercise both dashboard and restricted public chat; inject foreign-tenant/foreign-chatbot candidates and forged canonical metadata; reject stale deleted/superseded/retired-model sources and a deleted chatbot; verify failed/disconnected partial citations; and exercise a configured fallback with no renderable evidence. No private model input is written to these artifacts or added to an API response.

Existing RAG safety/injection, authorization, widget capability isolation, conversation failure/usage/rate-limit/cancellation and log-hygiene tests pass. The unchanged browser suite verifies playground streaming/history/feedback and widget operation on HTML/Next.js, mobile/focus, safe hostile text, sessions and instance isolation. These demonstrate the exercised boundaries only; they do not certify universal model behavior or browser security.

The original 100-case retrieval fixture remains unchanged: local hash/lexical Recall@5 **68/80 (85%)**, zero leaked chunks in that fixture. Its semantic live metrics remain null/BLOCKED. Neither this historical retrieval shortfall nor demo-generated citations are presented as semantic A2 success; see [new aggregate metrics](evidence/AUD-02/full/rag_metrics.json). Original audit results were not replaced.

## AUD-01 preservation

All 18 unchanged A1 tests pass twice, including pool-size-one lifecycle, bounded pool wait, post-embedding authorization mutations, remote-query cancellation/watchdog cleanup, capacity and two-tenant fairness. Final full-run capacity observations:

- Concurrency 1, ten requests: 10 completed / 0 rejected / 0 failed; success P95 36.91 ms.
- Concurrency 10, ten requests: 10 completed / 0 rejected / 0 failed; success P95 253.38 ms.
- Concurrency 50, fifty requests: 44 completed / 6 controlled rejections / 0 failed; success P95 1,219.05 ms, rejection P95 1,049.91 ms.
- Concurrency 100, one hundred requests: 48 completed / 52 controlled rejections / 0 failed; success P95 1,799.25 ms, rejection P95 1,535.98 ms.

All unchanged gates passed (success P95 <=2,000 ms, rejection P95 <=3,000 ms, required acceptance floors). Each stage ended with zero pool checkouts and equal checkouts/checkins; peak occupancy was eight of ten in these final stages. During saturated tenant A streams, tenant B completed 20/20 reads and 5/5 chats; busy read P95 5.69 ms versus idle 5.06 ms. See `full/capacity-*.json`, `full/fairness.json`, `full/pool-one.json` and `full/query-cancellation.json`. These are short local fixtures, not a production throughput guarantee. The preceding selected run is retained separately under `existing/`.

## Final commands and actual results

Commands ran from the repository root with the existing local Compose stack. Fixtures create/drop isolated migrated test databases and use Redis DB 15; backend suites were run serially. The full run additionally exercises existing local Celery/object-store ingestion. Browser tests use separate local fictional accounts. Full command metadata and sanitized logs are adjacent under `evidence/AUD-02/`; durations below are pytest durations unless explicitly marked wall time.

```powershell
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py::test_citations_must_only_reference_sources_actually_rendered tests/unit/mvp_improvement/test_rendered_evidence.py tests/integration/api/mvp_improvement/test_citation_provenance.py -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-02-focused-final.xml
```

**33 passed**, 4.21 seconds, exit 0. [Log](evidence/AUD-02/focused-final.log), [JUnit](evidence/AUD-02/focused-final.xml).

```powershell
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/mvp-improvement/AUD-02-existing api pytest tests/unit/rag tests/unit/test_chat_provider.py tests/integration/api/rag_eval tests/integration/api/test_conversations.py tests/integration/api/test_auth.py tests/integration/api/test_route_permissions.py tests/integration/api/test_widget.py tests/integration/api/mvp_improvement/test_chat_capacity.py tests/integration/api/mvp_improvement/test_chat_lifecycle.py -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-02-existing.xml
```

**287 passed**, 53.75 seconds, exit 0; includes all 18 A1 tests. [Log](evidence/AUD-02/existing-and-a1.log), [JUnit](evidence/AUD-02/existing-and-a1.xml).

```powershell
docker compose exec -T -e LIVE_INGESTION=1 -e AUDIT_OUTPUT_DIR=/tmp/mvp-improvement/AUD-02-full api pytest -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-02-backend-full.xml
```

**635 passed / 1 failed / 0 skipped**, 135.28 seconds, exit 1. Sole failure: `tests/unit/audit/test_prompt_evidence.py::test_production_embedding_transport_must_require_https` (AUD-03), `DID NOT RAISE ValidationError`. This test, embedding transport implementation and settings are unchanged. The log also retains a non-failing local HTTP request-processing shutdown notice. [Log](evidence/AUD-02/backend-full.log), [JUnit](evidence/AUD-02/backend-full.xml).

```powershell
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy
```

**PASS**, exit 0: all Ruff checks passed, 169 files already formatted, strict mypy no issues in 168 source files. The capture command checks each exit code before continuing. [Log](evidence/AUD-02/static-verified.log).

```powershell
corepack pnpm --filter @acs/web exec playwright test --reporter=json
docker build --target runtime -t acs-api:mvp-a2-local services/api
docker compose exec -T api python -m app.cli check-rls
```

Browser: **5 expected / 0 unexpected / 0 flaky / 0 skipped**, exit 0, wall 14.854 seconds. Runtime build and RLS check: **PASS**, exit 0, combined wall 5.302 seconds. Build is local only. [Browser log](evidence/AUD-02/browser.log), [build/RLS log](evidence/AUD-02/build-rls.log).

The focused command is also a reproducible deterministic demonstration: its plain synthetic provider emits valid `[1]`, omitted `[2]`, malformed `[01]` and unknown `[999]` in split deltas. Tests prove only `[1]` survives and its source exists in the exact provider input, SSE and stored transcript. No external model/configuration is needed.

To capture another run without touching historical artifacts:

```powershell
& services/api/.venv/Scripts/python.exe docs/mvp-improvement/tools/capture_a2.py verification-rerun 'docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py::test_citations_must_only_reference_sources_actually_rendered tests/unit/mvp_improvement/test_rendered_evidence.py tests/integration/api/mvp_improvement/test_citation_provenance.py -q --tb=short'
```

Choose a new evidence ID/output path on subsequent runs; do not overwrite audit or prior run artifacts. `capture_a2.py` records command, exit code, wall duration and redacted output. Artifact copies used `docker compose cp` from the distinct A2 `/tmp/mvp-improvement/` paths. The metadata JSON files retain exact executed command strings, including exit checks.

Final preservation/artifact verification also ran successfully:

```powershell
& services/api/.venv/Scripts/python.exe docs/mvp-improvement/tools/verify_a2.py
```

Actual result: **PASS**, 331 protected existing files unchanged; only the three expected application files differ in the 334-file baseline inventory. The bounded high-confidence credential/token scan found zero matches in A2 artifacts. The scan covers credential-bearing database URLs, bearer/session tokens and provider-key patterns; it is not a repository-history secrets audit. Artifacts contain fictional test data, aggregate metrics, test results and hashes rather than private customer model inputs.

## Retained failed attempts

- Baseline: the expected original AUD-02 failure, before code edits.
- First new-test run: 22 unit passes / ten integration setup errors because the new fixture attempted identical file contents twice and correctly hit existing duplicate-upload protection. Fixture content was made distinct; duplicate protection was not changed.
- Second new-test run: 31 passes / one failure because the new metadata fixture exceeded the existing 300-character title constraint. Corrected it to a legal 300-character title with a smaller configured input budget; the application constraint was preserved. The next focused run passed all 33 checks including the original regression.
- Initial static attempts found only new-test typing issues (deliberate frozen mutation and untyped positional row expansion). The negative frozen mutation has a narrow mypy suppression, and the fixture now constructs named typed fields. Final Ruff/format/mypy pass. Earlier logs remain under `static-first` and `static-final`; the successful final record is `static-verified`.

No acceptance criterion or existing test was relaxed. Reruns are not counted as additional distinct coverage.

## Remaining risks, rollback and stop boundary

Provenance proves a marker names evidence actually supplied, not that its factual claim is supported by that evidence. Live semantic evaluation remains separately BLOCKED. Public-domain authentication, proxy trust, embedding HTTPS enforcement, parser isolation, inbox features and widget loader lifecycle remain outside this task. In particular **AUD-03 remains FAIL**, unmodified. The 85% hash retrieval baseline remains below its separate target.

The canonical query adds bounded setup work; the measured default-pool and pool-one regressions pass, but sustained deployment load remains unverified. Marker parsing deliberately discards incomplete/nested/overlong bracket groups, so unusual noncitation bracket prose may be omitted. Provider/client disconnects and database outages retain A1's existing conservative accounting/finalization limitations; this is not hard-process-crash recovery or a new transactional delivery guarantee.

No schema migration is needed for rollback. The pre-A2 local `acs-api:mvp-a1-local` image, ID `sha256:bd672ba2d20727378b05723469f950dbd0512f00d976cca46728548b39eeabe6`, has all three affected file hashes equal to the captured A2 baseline; [verification](evidence/AUD-02/rollback-image.log). Restore these three files together from a verified A1 backup/image if necessary, preserving A1 lifecycle code and all stored messages/usage. A bind mount overrides image code, so retagging alone does not restore this workspace. Do not use the older pre-A1 audit image as the A2 rollback, delete volumes or rewrite historical citation snapshots. No rollback was performed.

**Stop: AUD-02 implementation and local validation are complete.** No AUD-03 or later work, paid-provider configuration, external deployment or push was performed. Original audit evidence and completed AUD-01 artifacts remain intact.
