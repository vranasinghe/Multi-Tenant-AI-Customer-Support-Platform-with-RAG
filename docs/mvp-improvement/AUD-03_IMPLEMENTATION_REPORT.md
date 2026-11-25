# AUD-03 — AI provider transport security

Date: 22 November 2026 (Asia/Colombo). Scope: Milestone A3 / AUD-03, Section 8 of the approved implementation plan.

## Decision

**AUD-03: PASS for the declared local transport/security tests and final validation.** Final full backend: **795 passed / 0 failed / 0 errors / 0 skipped**, pytest 141.06 seconds, exit 0. All **159 new transport tests**, all **18 AUD-01 tests**, all **32 AUD-02 tests**, and both unchanged original audit regressions pass. Backend Ruff/format/strict mypy, final runtime build and RLS validation pass. All **five existing browser tests** pass in the final address-corrected run.

Two preceding full runs missed the existing A1 P95 gate (2,004.02 and 2,011.51 ms against 2,000); their failures and measurements remain in the evidence. The unchanged isolated A1 rerun and final full confirmation pass. This PASS does not establish stable production latency or erase observed timing variability. No threshold, admission setting or assertion was relaxed.

## Baseline and root cause

Read the master improvement plan, approved implementation plan (particularly Section 8), progress tracker, completed AUD-01/AUD-02 reports, original security audit and prioritized fix plan. Inspected provider settings, both adapters, query subprocess/parent, API factory, worker factory/runtime, Dockerfile/Compose, environment examples and relevant tests. No root or ancestor `AGENTS.md` was found; frontend code was not changed.

Before application edits, recorded SHA-256 hashes of 399 existing files and ran the unchanged original regression. Settings inspection reported **local**, **demo LLM**, **hash embeddings**, and **both real-provider-key-presence flags false**. Actual baseline: **one failure**, pytest 0.52 seconds, command exit **1**, wall 4.988 seconds. The test reported `DID NOT RAISE ValidationError`. [Baseline command/log](evidence/AUD-03/baseline.json), [output](evidence/AUD-03/baseline.log), [JUnit](evidence/AUD-03/baseline.xml).

```powershell
Get-Content docs/audit/tools/environment.py | docker compose exec -T api python -
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py::test_production_embedding_transport_must_require_https -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-baseline.xml
```

The capture command checked the first exit code before running pytest. No API key or database password was displayed. Credentials used by new network tests are fictional; their endpoints are in-memory mock transports or loopback servers.

Root cause: production settings rejected the local hash baseline but did not validate the embedding endpoint's transport. `OpenAICompatibleEmbedder` accepted HTTP by prefix and sent a Bearer credential plus document/query text through `urllib.request.urlopen`, whose default opener follows redirects and discovers environment proxies. The finding was conditional on operator configuration; no real secret disclosure was observed or performed. The chat adapter already disabled redirects/proxy inheritance and used certificate verification; those controls were preserved.

## Modified files

Existing application files:

- `services/api/app/core/config.py`: shared endpoint-policy validation at Settings construction; explicit development opt-in; suppress raw validation-input display; callable revalidation for factories.
- `services/api/app/rag/embeddings.py`: secured synchronous httpx2 transport, bounded operations/response reads, sanitized failures, approved local policy propagation; unchanged embedding protocol/model identity/batch ordering/dimensions.
- `services/api/app/integrations/llm.py`: shared policy revalidation and explicit `verify=True`; existing redirect/proxy/retry/SSE behavior retained.
- `services/api/app/services/chat_work.py`: pass the approved local-policy flag through private query-child stdin; cancellation/admission/environment whitelist unchanged.
- `services/api/app/main.py`: validate explicitly supplied settings before API construction/logging/resource setup.
- `services/api/app/workers/celery_app.py`: validate provider settings before Celery configuration, including explicit settings objects.

Existing test fixture adaptations:

- `services/api/tests/unit/rag/test_embeddings.py`: replace urllib mock fixtures with httpx2 MockTransport fixtures while preserving batching/order, status taxonomy, network failure, malformed/shape, dimensions and key assertions. The invalid-scheme assertion now matches the HTTPS policy message.
- `services/api/tests/integration/api/mvp_improvement/test_chat_lifecycle.py`: **only three explicit loopback HTTP opt-in entries** in the existing two constructor fixtures and standalone child payload. Removing those three entries reconstructs the exact pre-A3 file hash. All 18 A1 assertions and timing gates are preserved; no production or general HTTP exception was added.

Configuration/docs: `.env.example`, `docker-compose.yml`, `docs/CHAT_ENGINE.md`, `docs/INGESTION.md`, `docs/DEVELOPMENT.md`, `docs/mvp-improvement/02_PROGRESS_TRACKER.md`.

New files:

- `services/api/app/core/provider_urls.py` — common operator-only URL policy.
- `services/api/tests/unit/mvp_improvement/test_provider_transport.py` — **159 new deterministic transport cases** in final code.
- `services/api/tests/support/provider_server.py` — bounded loopback test server, no request logging.
- `services/api/tests/support/provider_tls/{ca.pem,valid.pem,expired.pem,wrong.pem,fixture-key.pem,README.md}` — synthetic test-only certificates and deliberately public leaf key. CA signing key discarded.
- This report; `docs/mvp-improvement/tools/{capture_a3.py,generate_a3_tls.py,verify_a3.py,check_a3_resolution.py,playwright_a3.config.ts}`; new evidence under `docs/mvp-improvement/evidence/AUD-03/`.

No migration, dependency upgrade, embedding-space change, source citation schema, frontend/widget bundle, parser isolation, proxy-trust implementation, inbox or loader-lifecycle change was made. `services/api/Dockerfile`, original audit reports/evidence, both original audit regressions, completed A1/A2 reports/evidence, all A2 implementation/test files and A1 capacity tests remain unchanged. `query_process.py` continues to instantiate the same adapter from private stdin; it needs no separate transport implementation.

## Security policy

Configured chat/embedding adapters use one canonical URL policy. HTTPS is required by default in every environment. **Production and staging reject HTTP and reject `ALLOW_INSECURE_LOCAL_PROVIDERS=true`**, even if a network adapter is not selected. API and background-worker Settings loading and factories enforce the policy before remote operations. Builders also revalidate explicitly supplied settings, and chat validates again before streaming.

The policy rejects userinfo (including password-only, empty and encoded forms), query strings/empty query delimiters, fragments, whitespace/control characters, backslashes, percent encoding, non-ASCII host spellings, malformed DNS labels, invalid/ambiguous hosts and ports, unbracketed/zoned IPv6, dot segments and doubled path separators. Valid ASCII DNS/IDNA-punycode names, canonical IP literals, ports 1–65535 and simple base API paths are supported. Hosts are canonicalized and trailing path slashes normalized. Conservative path syntax accepts letters/digits, slash, underscore, dot, tilde and hyphen. Settings/errors name the relevant policy/field without echoing a supplied endpoint or credential.

The opt-in is **false by default**, wired through Compose's existing shared API/worker/beat environment. Only local/test settings may enable HTTP, and then only `localhost`, canonical IPv4 loopback (127/8) or IPv6 `::1`. Mapped IPv6, container service names, `host.docker.internal`, LAN/public addresses and wildcard listening addresses are not exceptions. No tenant can choose a provider URL or enable this operator setting. The low-level test adapter's explicit loopback flag is used by synthetic fixtures; runtime factories derive it only from validated Settings. Local HTTP support is a deliberate expansion of the prior chat settings policy, not a previously existing capability.

Embedding transport uses installed **synchronous httpx2**, `verify=True`, `follow_redirects=False`, `trust_env=False`. Chat retains these same controls. Every redirect is rejected, including same-host, cross-host and HTTPS-to-HTTP 301/302/303/307/308. Credentials or text are never replayed to a redirect destination. Ambient HTTP(S)/ALL_PROXY, NO_PROXY, SSL_CERT_FILE and SSL_CERT_DIR do not change provider routing/trust. No insecure TLS option or new proxy configuration is introduced.

Provider configuration is operator-controlled; HTTPS private services remain supported. This is not the crawler's public-IP/SSRF policy, a DNS-pinning scheme or a network sandbox. `localhost` is an explicit local-name exception, not protection from a compromised local resolver/host.

## Timeouts, taxonomy and compatibility

Embedding connect/read/write/pool operations are bounded by the existing timeout; connect is additionally capped at five seconds. Each response read checks a monotonic request deadline and an aggregate 32 MiB response ceiling. An already blocked read may add up to one read-timeout interval beyond that deadline. A batch has its own request budget; this is not a hard worker job deadline or memory/process sandbox. The query child retains its independent hard watchdog and the parent kill/reap behavior. AUD-05 remains unimplemented.

Compatible 2xx embedding responses retain their previous success behavior when their JSON/vector shape is valid. HTTP 429/5xx and network/TLS/timeouts remain transient `embedding_failed`; other statuses, including all redirects, are permanent `embedding_failed`. Malformed JSON retains its prior transient classification; malformed vectors/shape remain permanent. Client errors/exception chains contain fixed details, not URLs, provider bodies, keys or documents. No new retry loop was added; ingestion's existing bounded retries remain authoritative. Chat's pre-output retry policy and prohibition on retrying partially emitted answers remain intact.

Request payload fields, configured dimensions, batch size, model ID, response-index ordering and query/document interfaces are unchanged. Fixed 1536-dimensional database compatibility remains enforced by `build_embedder`; changing transport alone requires no reindex. Existing wrong-dimension/malformed payload tests still pass. The query parent sends the same settings through private stdin, including the bounded local opt-in; credentials are not placed in argv or logs, proxy/trust environment remains excluded and no database client is inherited.

Compatibility limits are documented in DEVELOPMENT.md section 9: use the final HTTPS endpoint directly; endpoints requiring query-based versions, encoded paths, non-Bearer authentication, enterprise proxy or custom CA configuration need separately reviewed support. The default HTTP client's installed trust bundle is used; ambient CA/proxy overrides are intentionally unsupported. Container loopback names the container, not the desktop host. Fix certificates/routing rather than expanding HTTP exceptions or disabling TLS. No paid provider, reindex, new model or provider reachability claim is included.

## New test coverage and privacy

The 159 new cases cover production/staging rejection, both providers' valid HTTPS configurations, malformed/unsafe URL components, local/test restrictions, all five redirect statuses with same/cross-host and downgrade destinations, real TLS trust/hostname/expiry, real HTTPS-to-HTTP redirect rejection, ignored proxy/CA environment, connection/read/TLS failures, real read timeout, slow-drip deadline/resource closure, 1536-d batching/order/model payload identity, compatible success statuses, API/worker startup, query-child routing/trust and partial-output chat failure without retry.

The real TLS tests trust a synthetic CA **only through an injected verifying test transport**. Trusted chain succeeds; default/untrusted CA, expired leaf and wrong SAN fail before an HTTP request carries credentials/text. Five actual TLS redirect tests record one authorized source request and **zero destination requests**. Mock redirect tests separately exercise both adapters and count exactly one request. These are local test observations, not remote-provider availability or Internet interception tests.

The certificate fixture initially failed strict OpenSSL verification because its CA lacked key-usage extensions; corrected CA/leaf extensions rather than weakening client verification. The initial tests also exposed Python's IPv4-mapped IPv6 loopback classification; the policy now explicitly accepts only IPv6 `::1`. Repeated fixture subjects required an explicit test-CA issuance setting. No CA key remains in the repository, no system trust store was edited and no test disables certificate verification. The public leaf key is test material, not a deployment credential. Certificates are time-bound; README records dates and regeneration steps.

Fictional secret/document markers are checked against captured logs and formatted exception output. Provider bodies/low-level exception chains are not logged or returned. Settings suppress raw-input display in normal exception strings, proven in fresh API/worker startup subprocesses. Structured `ValidationError.errors()`/JSON can still contain input unless explicitly omitted: documentation prohibits configuration dumps and explains `include_input=False` and omitted context. This is not a complete secrets-history scan or a guarantee against arbitrary external HTTP debug instrumentation.

## Execution history and reproducibility

All commands run at the repository root in the existing local stack. Backend fixtures create/drop isolated migrated test databases and use Redis DB 15, serially. Full runs include local Celery/object-store ingestion. Mock transports and loopback servers use synthetic credentials only. Original audit output paths are not reused. Captured command metadata/logs retain actual exit codes and wall durations; XML provides test-level results. Reruns are not additional distinct test coverage.

- `baseline`: one expected original AUD-03 failure, exit 1, before application changes.
- `initial`: 48 passes, exit 0, including both original audit tests and existing embedding/config/chat/worker checks.
- `transport-first`: 147 passes / eight failures, exit 1 (mapped IPv6 acceptance and strict test-certificate issues); preserved.
- `transport-second`: 155 passes, exit 0 after corrections.
- `transport-final`: 159 passes, exit 0 (157 then-current new cases plus both original audit tests).
- `static-first`: lint/format pass, mypy five errors because the decorated validator was called as an ordinary method. Split the model-validator hook from its typed callable method; no type ignores were added to application code.
- `static-final` and `release-static`: Ruff/format/mypy pass. Final checks: **173 files already formatted**, **171 source files with no mypy issues**.
- `preservation`: **362 passes**, pytest 59.50 seconds, exit 0; all 18 A1, all 32 A2, both original audit tests, auth/RAG/worker/widget/chat coverage.
- `backend-full`: **793 passes / zero failures/skips**, pytest 138.57 seconds, exit 0. Subsequently retained legacy embedding 2xx success compatibility with two additional cases.
- `backend-final`: **794 passes / one failure / zero skips**, pytest 148.93 seconds, exit 1. A1 100-concurrency success P95 **2,004.02 ms** exceeded the unchanged 2,000 ms gate. No citation/transport/auth failure occurred. Local fixture BrokenPipe shutdown output was also retained. The cause of this timing variation is not proven.
- `strict-rerun`: **18 A1 passes**, pytest 19.45 seconds, exit 0; no code/settings/threshold changes between the failed gate and this rerun.
- `backend-release`: **794 passes / one failure / zero skips**, pytest 155.12 seconds, exit 1. The same A1 P95 gate measured **2,011.51 ms**; all new security/citation tests passed. No code or thresholds changed afterward.
- `backend-confirmation`: **795 passes / zero failures/errors/skips**, pytest **141.06 seconds**, command wall **145.414 seconds**, exit **0**. This final all-passing snapshot includes the final 2xx compatibility cases.
- `original-after`: unchanged AUD-03 test explicitly rerun alone: **one pass**, pytest **0.18 seconds**, exit **0**, wall **3.506 seconds**. Its source hash is unchanged from baseline.
- `build-final`: final-source runtime image build and FORCE RLS verification both pass, combined wall **5.218 seconds**, exit **0**.
- `browser`: **zero passes / five failures**, exit 1, wall 193.272 seconds. The default localhost route reached an IPv6 Next.js server returning `/signup` 404; the project Docker web port is IPv4-only. `browser-resolution.log` records localhost/::1 404 versus 127.0.0.1 200 with the expected Create account title.
- `browser-ipv4`: **three passes / two failures**, exit 1. My first routing correction changed the API URL to 127.0.0.1, causing the two tests that share localhost session cookies to correctly receive 401. This was a QA-harness mistake, not a reason to weaken cookie or authorization rules.
- `browser-confirmation`: **five passes / zero unexpected/flaky/skipped**, exit **0**, wall **13.888 seconds**, after preserving localhost URL/cookie/origin semantics and selecting IPv4 routing in Chrome and Node. No frontend source, CORS/cookie setting or existing browser test assertion was changed; the IPv6 server was left running.

Relevant recorded commands:

```powershell
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py tests/unit/mvp_improvement/test_provider_transport.py -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-transport-final.xml
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/mvp-improvement/AUD-03-preservation api pytest tests/integration/api/mvp_improvement tests/unit/mvp_improvement/test_rendered_evidence.py tests/unit/audit/test_prompt_evidence.py tests/unit/rag tests/unit/test_chat_provider.py tests/unit/test_config.py tests/unit/test_celery.py tests/integration/api/rag_eval tests/integration/api/test_auth.py tests/integration/api/test_route_permissions.py tests/integration/api/test_widget.py tests/integration/api/test_conversations.py tests/integration/api/test_knowledge_jobs.py -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-preservation.xml
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/mvp-improvement/AUD-03-strict-rerun api pytest tests/integration/api/mvp_improvement/test_chat_capacity.py tests/integration/api/mvp_improvement/test_chat_lifecycle.py -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-strict-rerun.xml
docker compose exec -T api ruff check .
docker compose exec -T api ruff format --check .
docker compose exec -T api mypy
```

Use a new evidence ID and a fresh `/tmp/mvp-improvement/AUD-03-*` output path for subsequent reruns. `capture_a3.py` records commands/exit codes/timing and redacts credential-bearing database URLs and Bearer/session tokens; `verify_a3.py` checks the bounded preservation inventory and high-confidence artifact token patterns. Neither tool writes original audit or prior milestone evidence. Tests are reproducible with the existing installed dependencies and checked-in synthetic TLS fixtures; no paid model or OpenSSL executable is required to run the tests (OpenSSL was used only for one-time fixture generation).

## Final validation and AUD-01/AUD-02 preservation

```powershell
docker compose exec -T -e LIVE_INGESTION=1 -e AUDIT_OUTPUT_DIR=/tmp/mvp-improvement/AUD-03-confirmation api pytest -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-backend-confirmation.xml
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py::test_production_embedding_transport_must_require_https -q --tb=short --junitxml=/tmp/mvp-improvement/AUD-03-original-after.xml
docker build --target runtime -t acs-api:mvp-a3-local services/api
docker compose exec -T api python -m app.cli check-rls
```

[Final backend output](evidence/AUD-03/backend-confirmation.log), [JUnit](evidence/AUD-03/backend-confirmation.xml), [explicit original-test output](evidence/AUD-03/original-after.log), [final build/RLS output](evidence/AUD-03/build-final.log). Exact command strings, exit checks and wall times are in adjacent JSON metadata. The image was built locally, not deployed or pushed.

Final default-pool capacity observations (same 2,000/3,000 ms gates and acceptance floors):

- Concurrency 1: 10 completed / 0 rejected / 0 unexpected failures; success P95 **52.64 ms**.
- Concurrency 10: 10 completed / 0 rejected / 0 unexpected failures; success P95 **285.84 ms**.
- Concurrency 50: 42 completed / 8 controlled rejections / 0 unexpected failures; success P95 **1,294.65 ms**, rejection P95 **1,062.45 ms**.
- Concurrency 100: 48 completed / 52 controlled rejections / 0 unexpected failures; success P95 **1,925.10 ms**, rejection P95 **1,877.16 ms**.

All final stages ended with zero outstanding checkouts and equal checkout/checkin counts; peak occupancy was nine of ten. Tenant B completed **20/20 reads and 5/5 chats** while tenant A streams were held; busy read P95 **7.09 ms** versus idle **5.44 ms**. Pool-one, watchdog, cancellation, post-embedding auth changes, lease cleanup and usage checks passed. See `confirmation/capacity-*.json`, `fairness.json`, `pool-one.json` and `query-cancellation.json`. The failed runs also recorded zero unexpected request failures and balanced pool counts; their timing gates still failed and are not reclassified as passes. No causal explanation for the variation is claimed.

The final browser command uses a documentation-side QA config importing the existing project config/tests, disabling only native-server startup (the Docker web is already running) and supplying Chrome's localhost IPv4 mapping. Node's DNS result order is set for the QA process, with the API URL still localhost:

```powershell
$env:E2E_API_URL="http://localhost:8000"
$env:NODE_OPTIONS="--dns-result-order=ipv4first"
corepack pnpm --filter @acs/web exec playwright test --config ../../docs/mvp-improvement/tools/playwright_a3.config.ts --reporter=json
```

[Final browser output](evidence/AUD-03/browser-confirmation.log) and [routing observation](evidence/AUD-03/browser-resolution.log) preserve the distinction between failed default routing, the incorrect API-host experiment and the passing run. Failed-run generated trace files were not copied into sanitized evidence; logs retain actual failure details. The temporary documentation-side trace directory was removed after verifying its exact workspace path. Normal Playwright artifacts remain in the existing ignored test-results location. The harness does not alter backend provider transport policy or stop another process.

All 32 A2 tests and the original omission regression pass in final JUnit. A2 prompt rendering, source authorization, marker parsing, conversation orchestration/persistence and their tests are byte-for-byte unchanged by A3. Semantic citation accuracy remains BLOCKED, not inferred from scripted responses.

## Remaining limitations and stop boundary

Local TLS/configuration tests cannot establish production egress, Internet provider uptime, semantic retrieval/answer quality, model prompt-injection obedience or semantic citation accuracy. Those live/model/deployment checks are not run or remain BLOCKED without separately authorized resources. The existing hash retrieval fixture's separate 85% result is not improved or reclassified by A3.

The A1 near-threshold timing failure remains a material local load-test observation even after passing reruns. No admission/pool setting, assertion or threshold was changed to obtain a pass; sustained deployment throughput remains unverified. HTTP localhost relies on local resolver/host integrity. TLS uses normal CA/hostname/expiry verification, not certificate pinning or custom revocation policy. OS/network-level routing and arbitrary trusted-code test-transport injection are outside the ambient proxy/environment guarantee.

AUD-04 proxy trust (including the unchanged wildcard runtime command), AUD-05 parser containment, AUD-06 inbox, AUD-07 widget loader lifecycle and Milestones B–J remain unimplemented by this work. No external deployment, paid-provider configuration, push, migration or original audit rewrite occurred. Overall MVP readiness remains **NOT READY**; Milestone A is incomplete.

There is no `.git` in this workspace. Rollback must restore a consistent reviewed code/configuration snapshot, retain all published vectors/messages/usage and preserve A1/A2 lifecycle/citation fixes. No data migration/reindex is required for this transport-only change. Do not restore HTTP production transport, disable TLS verification, delete volumes or restore a pre-A1 image as a convenience rollback. Prefer fixing a final HTTPS endpoint/certificate or disabling the affected provider until repaired. No rollback was performed.


Final bounded verification command:

```powershell
& services/api/.venv/Scripts/python.exe docs/mvp-improvement/tools/verify_a3.py
```

Actual verification: **PASS**, 385 protected existing files unchanged out of the 399-file baseline; exactly the 14 expected existing files changed (including tracker/docs/test fixture adaptations). Zero high-confidence token/credential findings in the new evidence. The A1 fixture-only reverse hash matches and all final test groups match their recorded counts. This is bounded verification, not a history-wide secrets audit.

Local artifact closure: see [results](evidence/AUD-03/results.json) and [preservation/sanitization inventory](evidence/AUD-03/artifact-validation.json). `verify_a3.py` compares the 399-file baseline inventory, checks the A1 fixture-only reverse hash and final JUnit groups, and scans new evidence for high-confidence credential/token patterns. This bounded scan does not replace a repository-history or external secret-store audit.

**Stop after AUD-03:** implementation and local validation are complete. Do not start AUD-04 or any later milestone automatically.
