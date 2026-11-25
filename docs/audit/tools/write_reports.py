"""Render audit reports from captured evidence; never invokes application services."""
from pathlib import Path
import ast
import csv
import json
import statistics
from collections import Counter

ROOT = Path('docs/audit')
E = ROOT / 'evidence'
summary = json.loads((ROOT / 'test_results.json').read_text())
performance = json.loads((E / 'performance.json').read_text())
results = json.loads((E / 'rag_results.json').read_text())
workflow = json.loads((E / 'business_workflow.json').read_text())

def write(name, content):
    (ROOT / name).write_text(content.strip() + '\n', encoding='utf-8')

score_lines = '\n'.join(f'- Phase {p}: {score:g}/{summary["phase_weights"][p] if p in summary["phase_weights"] else summary["phase_weights"][int(p)]}.' for p, score in summary['phase_scores'].items())

write('01_EXECUTIVE_SUMMARY.md', f'''
# Independent implementation audit — Phase 1–6

Audit date: 22 November 2026, Asia/Colombo. Decision: **NOT READY**. Evidence-supported rubric score: **80.5/100**. A high-risk availability defect and unverified real AI workflows prevent release regardless of the score.

## Results

{score_lines}

The rubric has ten equally weighted requirements per phase; a verified partial implementation earns half credit. Blocked or untested requirements earn zero. See [the complete matrix](02_PHASE_IMPLEMENTATION_MATRIX.md) and `implementation_matrix.json` for every item, source, status, evidence and action. These phase numbers follow the user's audit request; the repository roadmap uses a different numbering scheme beginning with Phase 0.

Coverage is **51/60 runtime-exercised rows**, five static-only and four blocked/untested. Runtime-exercised does not mean passed. Status distribution: 45 PASS, eight PARTIALLY_IMPLEMENTED, three FAIL, three BLOCKED, one NOT_TESTED. No percentage of source-line coverage is claimed.

All **807 original tests passed**: 582 backend, 213 web, seven widget and five browser. Four distinct additional audit checks end with one pass and three failures: **808 passed / 3 failed / 811 distinct checks**. Across reruns, 814 test invocations produced 809 passes and five failures. One initial failure was an audit DOCX fixture error corrected in the audit harness. The three final failures are reproducible application behavior, not that fixture error. See [execution records](12_TEST_EXECUTION_LOG.md).

## Release blockers and material findings

- **AUD-01 HIGH:** concurrent authenticated chat can exhaust the database connection pool before admission control. A fresh ten-request confirmation returned nine HTTP 500s; the first 10/50/100 concurrency stages returned only HTTP 500s. Logs show the 30-second QueuePool timeout. This threatens tenant availability.
- **AUD-02 MEDIUM:** prompt truncation can omit a selected source while citation validation still accepts its marker. Citation provenance is therefore not reliable in this boundary case.
- **AUD-03 MEDIUM:** production settings accept a plain HTTP embedding endpoint; if configured that way, document text and provider credentials can traverse an unencrypted connection. No real credential exposure was performed or observed.
- Other bounded findings: wildcard trusted proxy addresses, missing hard parser resource isolation, a placeholder conversation inbox and non-idempotent loader initialization. Static risks are distinguished from confirmed runtime defects in [the security report](05_SECURITY_AUDIT.md).

No cross-tenant leakage was observed in the tested retrieval, identifier-manipulation, RLS and public-widget cases. This is evidence for those cases, not a universal security guarantee.

## AI quality and working workflows

The configured environment uses the **demo LLM and hash-v1 embeddings**, with no real provider keys. All live answer correctness, faithfulness, semantic citation accuracy, refusal quality and model prompt-injection resistance are **BLOCKED**. Canned responses are reported separately and are never scored as real AI success.

A reviewable 100-question evaluation over 20 fictional TechMart/SkillHub documents measured **68/80 = 85% answer-bearing Recall@5** for the local hybrid retrieval baseline, below the proposed 90% target. Twenty unknown/adversarial cases are excluded from that denominator. The data and exact metric limitations are in [the RAG report](06_RAG_EVALUATION_REPORT.md).

The local foundation builds, migration/RLS checks, identity/tenant controls, document ingestion, stored vectors, conversation persistence, SSE plumbing and widget integration have substantial passing evidence. A real separate-origin plain HTML site and a Next.js page loaded and used the widget; mobile sizing, source display, anonymous resume, hostile text rendering and different-bot isolation passed. The named business workflow uses a disposable database; browser integration uses separate local test accounts. These are layered evidence, not one fabricated single-account live-AI journey.

## Scope and preservation

Reviewed plans, manifests/locks, frontend/backend source, migrations, workflows, infrastructure, existing tests and generated widget artifacts. Tests ran locally or in disposable fixtures; no production database or paid AI calls were used. New files are audit reports, fixtures and tests only. SHA-256 comparison of 242 pre-existing application/configuration files found **zero changed files** (`evidence/source_preservation.json`). No fixes or Phase 7 features were implemented.

The [prioritized fix plan](10_PRIORITIZED_FIX_PLAN.md) defines concrete release gates. Resolve the high-risk pool defect, align citations with rendered evidence, harden production transport and proxy boundaries, then evaluate an approved real provider on the supplied dataset before reconsidering MVP release.
''')

write('03_ARCHITECTURE_AUDIT.md', '''
# Architecture audit

Status: PARTIALLY_IMPLEMENTED for production readiness; substantial local architecture is verified. Source inventory: `evidence/source_inventory_before.json`. Runtime versions and safe configuration flags: `evidence/environment.log`. The existing draft architecture is a target design, not proof of implemented capabilities.

## Requirements and actual stack

Read `docs/PRD.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `DATABASE.md`, `API_SPEC.md`, `SECURITY.md`, `DECISIONS.md`, `DEVELOPMENT.md`, `INGESTION.md`, `CHAT_ENGINE.md`, `RAG_EVALUATION.md`, `WIDGET_DEPLOYMENT.md`, and earlier phase reports. Earlier success claims were independently checked against the current source and new executions.

- Web: Next.js 16.4.6 App Router, React 19.3.1, TypeScript 6, Tailwind 4 and reusable UI components. The dashboard talks to FastAPI; application authorization stays server-side.
- API: Python 3.13, FastAPI 0.165, Pydantic settings, SQLAlchemy 2.1.9 and Alembic 1.20.1. It is a layer-first modular monolith (`api`, `services`, `schemas`, `models`, `rag`, `integrations`, `core`, `workers`), rather than every future product domain in the draft architecture being complete.
- Data: PostgreSQL 18 with pgvector 0.8.7, tenant metadata and FORCE RLS; Redis 8.10.3 for queue/control state; Celery 5.7 API/worker/beat process types; S3-compatible storage with RustFS locally.
- Authentication: custom opaque, server-managed sessions in secure HttpOnly cookies; Argon2id password hashes and scoped one-use identity tokens. This is not an Auth.js implementation.
- Parsing: pypdf and bounded DOCX ZIP/XML parsing with defusedxml. PyMuPDF/python-docx from the planning material are not the actual extraction stack.
- Widget: vanilla TypeScript self-contained IIFE loader and iframe panel, served by the API. The planned Preact widget is not used. Built version 1.0.0 loader is 4,053 bytes gzip; version and size are in `services/api/widget_assets/v1/manifest.json`.
- AI: configurable OpenAI-compatible server-side adapter. Current execution uses `demo` generation and `hash-v1` embeddings; an implementation of the adapter is not evidence that real production models work.

Native host versions were Node 24.16.0, pnpm 11.25.0 and uv 0.10.8. Project tooling declares pnpm 11.28.12 and uv >=0.13. Recursive frontend commands were run through corepack; Python tests used the container. The older host tools are an environment discrepancy, not a demonstrated product failure.

## Implemented request/data paths

```mermaid
flowchart LR
    D[Next.js dashboard] -->|Cookie auth REST and SSE| A[FastAPI]
    H[Customer HTML or Next.js site] --> L[Public loader]
    L --> F[API-origin iframe]
    F -->|Scoped session token| A
    A --> P[(PostgreSQL and pgvector)]
    A --> R[(Redis controls and queue)]
    A --> S[(S3 originals)]
    R --> W[Celery ingestion worker]
    W --> S
    W --> P
    A --> M[Server-side LLM adapter]
```

Membership/role checks establish the tenant scope; tenant-bound queries and database RLS add independent enforcement. Storage keys and document versions scope original files and chunks. Retrieval combines vectors and PostgreSQL full-text search, filtering by organization, bot and current document version. Chat assembles a bounded context, streams SSE events, saves messages and accounts for usage. Public widget capabilities expose a narrower route family than dashboard sessions.

These boundaries have runtime tests. The chat path nevertheless holds a request-scoped database session while opening another session before admission control. At default pool limits this creates AUD-01. The source selection/prompt-rendering boundary also has AUD-02: the citation source set can exceed the evidence actually rendered.

## Build and operational validation

PASS: recursive frontend lint/typecheck/test/build; backend Ruff and mypy over app/migrations; runtime Docker image build; backend migration tests; health smoke and RLS check. `evidence/health_rls.log` records the six-revision schema, service checks and no unprotected tenant tables. `baseline.xml` includes migration and database tests. Docker image build does not prove production ingress, deploy automation or recovery works.

PASS within package-advisory scope: pnpm audit and pip-audit reported no known dependency advisories. Lockfiles/builds are exercised. Container base-OS vulnerabilities, future advisories and full supply-chain assurance are NOT_TESTED. No remote CI run is claimed: `.github/workflows/ci.yml` was inspected and local equivalents executed. Final full backend Ruff lint/format checks passed (162 files formatted); mypy passed for 161 source files. The dynamically typed integration audit harness explicitly opts out of strict type checking; the small unit regressions are typed. See `evidence/audit_static.log`.

Production concerns: HTTP embedding URLs are accepted (AUD-03), uvicorn trusts forwarded addresses from every peer (AUD-04), and file parsers lack a hard per-job CPU/memory/time isolation boundary (AUD-05). Application error/logging controls have tests; prompt/document contents must remain excluded from logs. External secret management, repository history, actual bucket/IAM policy, TLS termination, backups/restore and alerting are NOT_TESTED.

## Placeholders and scope boundaries

`integrations/llm.py` demo mode is intentionally canned. It must not be represented as factual AI capability. `components/conversations/conversations-screen.tsx:61` unconditionally displays an empty inbox with disabled filters even though API messages are persisted (AUD-06). Dashboard/roadmap descriptions of future billing, channels and analytics do not establish implemented Phase 1–6 behavior. Anonymous session retention limits access/resume; physical message deletion by a retention sweep was not verified and is absent from the reviewed Phase 6 flow. Strict grounding is effectively always enforced; its configurable appearance should be reconciled with product copy.

No architectural redesign was undertaken. The immediate plan preserves the modular monolith and corrects the measured session/admission and evidence boundaries before adding scope.
''')

write('04_FUNCTIONAL_TEST_RESULTS.md', '''
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
''')

# Actual category counts, with no fabricated semantic judgments.
categories = Counter()
for row in results:
    categories[row.get('category', 'unknown')] += 1
with (ROOT / 'rag_evaluation_results.csv').open(newline='', encoding='utf-8') as handle:
    csv_rows = list(csv.DictReader(handle))

write('06_RAG_EVALUATION_REPORT.md', '''
# RAG evaluation report

Live evaluation: **BLOCKED**. Runtime settings show no LLM or embedding provider key, `llm_provider=demo`, `embedding_provider=hash`. No paid model request was attempted. Demo output is a canned infrastructure response; it cannot establish answer correctness, faithfulness, semantic citation quality, refusal behavior or model prompt-injection resistance.

## Dataset and reproducibility

`rag_evaluation_dataset.jsonl` contains exactly **100 manually reviewable cases**. `rag_evaluation_corpus.json` contains twenty short fictional source documents: ten TechMart and ten SkillHub. Each case records organization, question, category, expected answer, expected document/phrases and optional conversation history. This is a transparent synthetic acceptance fixture, not a customer-domain benchmark or human-labeled production sample.

There are twenty cases each for factual, paraphrase, multi_fact, follow_up and unknown/adversarial questions. Eighty are answerable. Expected filenames and phrases make the labels reviewable; reviewers should revise the labels/corpus before drawing production generalizations. The follow-up retrieval probe explicitly prepends the prior user question to the current query. It therefore tests retrieval with that expanded query; it does not prove the production conversation engine performs equivalent query rewriting.

Run the business/evaluation command in report 12. It uploads/indexes the corpus in an isolated database, invokes the actual authenticated hybrid retrieval route with top_k=5, inspects persisted vectors and records actual returned chunks. No hand-authored retrieval results are substituted. The evaluation code is `services/api/tests/integration/api/audit/test_implementation_audit.py`; its local `dataset.json` mirrors the reviewable corpus/cases.

## Observed retrieval metric

Answer-bearing Recall@5 = answerable cases with at least one top-five chunk belonging to the expected document and containing all configured expected phrases, divided by 80. All phrases must occur in the same returned chunk. This is a **case hit rate**, not exhaustive recall over all relevant chunks. Unknown cases are excluded because they have no gold supporting source.

- Factual: 20/20.
- Paraphrase: 12/20.
- Multi-fact: 16/20.
- Follow-up with explicit prior-question expansion: 20/20.
- Total: **68/80 = 85%**, FAIL against proposed >=90% target.
- Cross-tenant leaked chunks in these 100 searches: **0**; PASS for this measured sample only.

This is the local hash-vector plus lexical full-text baseline. Hash embeddings are not semantic production embeddings. Replacing the embedding model requires reindexing the corpus and repeating the same protocol; these results cannot predict the new model's score.

## Live metric gates

- Answer correctness >=90%: BLOCKED; generated live answers absent, no pass denominator.
- Faithfulness >=95%: BLOCKED; requires claims to be judged against retrieved evidence.
- Citation accuracy >=95%: BLOCKED for semantic attribution; the deterministic provenance boundary separately FAILS AUD-02.
- Unknown-answer refusal >=95%: BLOCKED; twenty gold unknown/adversarial cases exist but no real model judgment was made.
- Tenant leakage =0: observed 0 in the executed retrieval sample and additional authorization tests. This is not proof against every attack.
- Recall@5 >=90%: measured 85% for the disclosed local baseline, FAIL.

Correctness should count fully correct answers among answerable cases; faithfulness should measure supported factual claims among generated claims; citation accuracy should measure correctly supported citations among all citations; refusal should count appropriate insufficient-evidence responses among the twenty unknown cases. Declare treatment of partial answers, empty denominators and judge disagreements before a live run. Use human review of the supplied expected answers/evidence, with adjudication of disagreements. No Ragas/LLM judge score is claimed.

## Results schema and latency

`rag_evaluation_results.csv` has 100 actual result rows: question/category/gold labels, retrieved chunks with IDs/content, retrieval status/failure reason, and live status/failure reason. Live `generated_answer` and `actual_citations` are null/unavailable. Separate `mock_generated_answer` and `mock_citations` columns preserve the infrastructure demo result without conflating it with a live answer. Every live row is BLOCKED. Evidence JSON is in `evidence/rag_results.json` and `rag_metrics.json`.

The 100 sequential retrieval API calls had median **9.98 ms** and empirical P95 **13.38 ms** in this local fixture. These include the route/authentication work with local hash embeddings; they exclude real embedding network latency. The follow-up mock generation does not replay history and is explicitly marked as such in each applicable row. Generated source IDs are local fixture IDs and are not durable customer URLs.

Structural prompt tests verify instruction/data separation and bounded context. They do not establish that a real model ignores malicious document instructions. The citation-budget regression proves a deterministic issue independently of model behavior. Full live evaluation remains a release gate.
''')

perf_table = ['| Concurrency | Requests | HTTP statuses | P50 ms | P95 ms | Successful TTFT P95 ms | Successful req/s | HTTP error rate | CPU s | Peak RSS KiB |', '|---|---|---|---|---|---|---|---|---|---|']
for p in performance:
    ttft = p['successful_ttft_p95_ms']
    perf_table.append(f"| {p['concurrency']} | {p['requests']} | {p['statuses']} | {p['p50_ms']:.2f} | {p['p95_ms']:.2f} | {ttft if ttft is None else round(ttft,2)} | {p['successful_requests_per_second']:.2f} | {p['http_error_rate']:.0%} | {p['cpu_seconds']:.4f} | {p['peak_process_rss_kib']} |")
write('07_PERFORMANCE_REPORT.md', '''
# Performance validation

Acceptance: **FAIL**. A HIGH database-pool starvation defect prevents safe chat admission under modest concurrency. Raw samples, statuses and process resource values are in `evidence/performance.json`; a fresh ten-request confirmation is in `performance_confirmation.json` and `pool_regression.log`.

## Environment and method

Local Docker stack, 32 logical CPUs reported to the container; PostgreSQL/pgvector and Redis are real. The harness invokes actual FastAPI routes through ASGI against a disposable database, using a deterministic LLM fixture with 10 ms delay, one text delta, and usage 100 input/10 output tokens. No paid API or high-volume real-model load was used. No reverse proxy, browser or provider network is included.

The default org generation concurrency cap of three is retained. Request/minute and monthly usage limits are raised only in the audit test so quota depletion cannot mask infrastructure bottlenecks. Database pool defaults remain five plus five overflow. Each stage issues max(10, concurrency) requests through a bounded semaphore; therefore 170 requests are measured across four stages. This is a short saturation probe, not a sustained production capacity benchmark. A 40-second stage deadline bounds hangs.

Duration is full request completion latency including failed responses, not pure generation time. TTFT is an ASGI send callback's first SSE delta, not browser-observed network TTFT. Percentiles use ordered index floor((N-1)*p), including the reported P50; small-sample values should not be overinterpreted. Successful rate is HTTP-200 completions divided by stage wall time; error rate includes HTTP >=400 or harness timeout. Status 200 alone would not prove a correct answer.

''' + '\n'.join(perf_table) + f'''

CPU is process RUSAGE_SELF elapsed CPU seconds per stage; it excludes database, worker and host CPU. RSS is the process lifetime peak, not a new per-stage allocation measurement. No container CPU utilization percentage is inferred from these values. Null TTFT means there were no successful streamed replies in that stage.

## Confirmation and root cause

The original 10/50/100 stages produced 160 HTTP 500 responses around the 30-second database-pool wait. A fresh ten-concurrent-request test produced **one HTTP 200 and nine HTTP 500s**, with P50 30,148.55 ms and P95 30,236.69 ms. The one success emitted its first delta only after about 30,287.92 ms. This schedule-dependent variation supports resource starvation rather than a deterministic provider rejection.

Tracebacks show `sqlalchemy.exc.TimeoutError`, QueuePool size 5 overflow 5, timeout 30 seconds. Authentication's request-scoped session retains a connection while chat preparation tries a second session in `find_conversation`, before admission control can reject excess requests. See AUD-01 for precise source locations, impact, proposed fix and regression criteria. Increasing the pool alone does not resolve the resource-ordering problem.

## Retrieval, document processing and unmeasured dimensions

One hundred sequential hash/hybrid retrieval API calls measured median 9.98 ms/P95 13.38 ms. Twenty tiny text document upload/controlled-processing operations measured median **{statistics.median(workflow['ingestion_ms']):.2f} ms**; raw values are in `business_workflow.json`. The latter uses the fixture object store and deterministic job drain and excludes distributed worker scheduling, S3 network and real embedding latency. PDF/DOCX persistence was verified separately without a general throughput claim.

Real model TTFT/generation latency, large-document throughput, sustained multi-tenant load, production proxy/network overhead, query EXPLAIN plans, per-query database timings, full worker/container resource metrics and long-term memory growth are **NOT_TESTED**. Successful HTTP-200 total response latency at concurrency one is the only full-chat local latency baseline here. After fixing pool ordering, repeat all stages and add a second-tenant read/health probe; overload must return controlled admission responses rather than HTTP 500s.
''')

write('08_WIDGET_VALIDATION_REPORT.md', '''
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
''')

missing = ['# Missing features and bugs', '', 'Audit only: no fixes or additional product scope were implemented. Findings are reproduced in report 05 with source locations and regression suggestions.', '']
for f in summary['findings']:
    missing += [f"- **{f['id']} {f['severity']} — {f['title']}**. {f['status']}. {f['impact']}"]
missing += ['', '## Blocked or unverified requirements', '', '- Real provider/semantic embeddings, factual answer quality, faithfulness, semantic citations, appropriate unknown-answer refusal and model-level injection resistance: BLOCKED. No approved live credentials are configured.', '- Local retrieval acceptance target: FAIL, 85% versus proposed 90%; genuine semantic-provider results cannot be inferred from the hash baseline.', '- Production ingress/proxy trust, secret-manager operations, cloud bucket/IAM policy, public DNS verification, remote CI/deployment, backups/restore and alerts: NOT_TESTED.', '- Full WCAG/assistive technology, console-error collection and broad browser/network failure recovery: NOT_TESTED.', '- Large-file parser hard CPU/memory/time limits and physical anonymous-message retention purge are not established.', '- Strict grounding is effectively always enforced despite appearing configurable; documentation/UI should communicate the supported behavior.', '', '## Placeholder boundaries', '', 'The conversation inbox is hardcoded empty, while API persistence and playground history do work. Treat the inbox gap as a UI completeness issue; do not implement advanced Phase 7 analytics during this audit. Demo LLM output is deliberately canned and is not evidence for AI quality. Planned billing/channels/analytics in the draft architecture are outside this Phase 1–6 implementation audit, not automatically defects in the requested current scope.', '', 'No confirmed CRITICAL leak was observed. Seven bounded findings include one HIGH; a lack of observed leakage does not eliminate the need for broader production assurance.']
write('09_MISSING_FEATURES_AND_BUGS.md', '\n'.join(missing))

write('10_PRIORITIZED_FIX_PLAN.md', '''
# Prioritized remediation plan

These are proposed changes for review after the audit. No application code was changed. The order follows risk and dependency; no delivery-date estimate is invented.

## P0 — release gates

1. **AUD-01 — API/database owner:** remove nested pool acquisition while an authenticated request transaction is held; release auth resources before streaming; apply admission controls before scarce-resource checkout. Preserve tenant-scoped session/RLS semantics and cancellation cleanup. Add bounded waits and controlled overload responses. Exit gate: repeat 1/10/50/100 local stages; zero unexpected 500s; documented 429/503 responses permitted; a second tenant remains responsive; quotas/leases reconcile after cancellation.
2. **AUD-02 — RAG/chat owner:** make prompt assembly return the exact rendered source set; compute escaped-content budgets consistently and validate citations against that set. Exit gate: current failing omission regression passes, including escaping/metadata/history edge cases, and no marker resolves to absent evidence.
3. **AUD-03/AUD-04 — platform/security owner:** reject HTTP provider endpoints in production, validate redirect behavior, restrict trusted proxies and enforce the direct-ingress boundary. Exit gate: failing HTTPS settings regression passes and an untrusted peer cannot choose its limiter IP using forwarded headers. Validate real deployment topology before release.
4. **Live AI verification — AI/QA owner:** configure an approved server-side model and embedding provider, reindex the supplied fictional corpus and run the 100-case evaluation. Review labels and grade real answers/claims/citations/refusals; retain model/version/settings and redacted results. Require >=90% correctness, >=95% faithfulness, >=90% Recall@5, >=95% citation accuracy, >=95% appropriate refusal and zero tenant leakage. If targets are revised, justify changes before evaluating rather than fitting them to results. No credential belongs in browser code or report logs.

## P1 — hardening and completeness

5. **AUD-05 — ingestion/platform owner:** isolate document parsing with hard wall-clock/resource budgets and cancellation/cleanup. Preserve existing magic-byte, zip and extraction limits. Test a bounded hostile/malformed fixture in a disposable worker and demonstrate queue recovery.
6. **AUD-06 — dashboard owner:** replace the unconditional empty inbox with the Phase 1–6 data actually promised, or clearly label its availability. Preserve stored conversations. Do not expand into Phase 7 analytics without a separate request. Test widget conversation visibility and refresh only if that UI is brought into current scope.
7. **AUD-07 — widget owner:** define repeated initialization semantics, make the default idempotent and add a teardown path; preserve intentionally separate bot instances. Test duplicate same-key scripts, navigation/remount and listener cleanup in plain HTML and Next.js.
8. **Platform/privacy/QA owners:** document physical retention behavior and implement it only in an authorized follow-up; verify public DNS lifecycle, bucket/IAM restrictions, restore drill, health/alerting, keyboard/assistive technology and browser network/console fault paths.

## Reverification gate

Run the current original suites and the deliberately failing audit regressions after fixes. Rerun targeted checks when changes affect their assumptions, then repeat the staged workload and real-provider dataset with explicit costs/limits. Retain before/after artifacts, distinguish fixture from real-provider results, verify source citations manually, and obtain a new readiness decision. A numeric score alone cannot waive unresolved HIGH risk or unverified critical end-to-end AI behavior.
''')

write('11_MVP_READINESS_REPORT.md', f'''
# MVP readiness decision

**NOT READY — verified rubric score 80.5/100.** The database-pool failure is HIGH risk and real AI workflows remain unverified. The numerical result cannot override either release gate.

{score_lines}

Scoring: ten equally weighted items per phase; PASS full credit; PARTIALLY_IMPLEMENTED half for the verified subpart; FAIL/BLOCKED/NOT_TESTED zero. Full row-level rationale is in report 02 and `implementation_matrix.json`. This is a disclosed audit rubric, not a product completion percentage or security certification.

Verification coverage: 51/60 rows exercised at runtime, five static-only, four blocked/untested. Of the 60 rows, 45 PASS, eight PARTIALLY_IMPLEMENTED, three FAIL, three BLOCKED and one NOT_TESTED. Existing checks cover identity, tenant defenses, ingestion, persistence and local embeds; production cloud operations and model semantics are outside that verified coverage.

Test counts: 811 distinct final checks, 808 passed and three failed. Total executions including reruns: 814, with 809 passes/five failures, including one corrected audit fixture failure. The 100 retrieval evaluation rows are separate from pytest counts. Builds, lint, types, package advisories and health/RLS checks passed with the scope documented in report 12.

Confirmed HIGH: AUD-01 request-session/pool starvation. Confirmed CRITICAL: none observed. Cross-tenant leaked chunks in the measured dataset: zero. Citation provenance fails AUD-02 and production embedding transport fails AUD-03. Other medium/static findings require deployment or isolation validation; their impact is conditional and is not described as an observed breach.

Live answer correctness, faithfulness, citation semantics, appropriate refusal and real model injection resistance are BLOCKED. The local hash/lexical retrieval baseline achieved 85% answer-bearing Recall@5, below the proposed 90% target. Consequently the crucial document-to-correct-answer workflow is not verified even though the local demo transport and external widget work.

Remaining production assurance includes trusted ingress, TLS/provider settings, secret storage, bucket/IAM boundaries, restore/alerts, parser isolation, full accessibility and fault recovery. Conversation-inbox and repeated loader initialization gaps are described in report 09. No Phase 7 implementation is required by this audit.

The path to reassessment is [report 10](10_PRIORITIZED_FIX_PLAN.md): fix the measured availability and evidence bugs, secure provider/proxy configuration, pass targeted regressions, repeat saturation with tenant fairness, then evaluate an approved real provider and verify production operational boundaries. No application fixes were made during this audit.
''')

commands = ['| ID | Actual command | Exit | Wall seconds | Evidence |', '|---|---|---|---|---|']
for c in summary['commands']:
    cmd = c['command'].replace('|', '\\|').replace('\n', ' ')
    commands.append(f"| {c['id']} | `{cmd}` | {c['exit_code']} | {c.get('duration_seconds','')} | `{c['log']}` |")
write('12_TEST_EXECUTION_LOG.md', '''
# Reproducible execution log

Commands below were actually executed from the repository root during this audit. Exit codes and wall times come from captured subprocess metadata, not estimated timings. Logs/JUnit are in `evidence/`. Environment was local Docker with loopback ports; no production database or paid model was used. The audit fixtures create/drop disposable databases, use isolated Redis test state and synthetic credentials. Browser tests create disposable local application accounts via Mailpit.

''' + '\n'.join(commands) + '''

## Counts and interpretation

- `baseline_backend`: 582 PASS, 90.62 seconds pytest time, with LIVE_INGESTION=1; captured JUnit `baseline.xml`.
- `frontend_tests`: 213 web + seven widget PASS. `browser`: five PASS, 12.3 seconds test time.
- `audit_runtime`: one PASS/two FAIL. The workflow failure was an audit fixture constructing DOCX paragraphs with the wrong shape, later corrected only in the added audit helper. The citation regression was an application failure. The performance function at this point only collected measurements; its PASS was not an acceptance result.
- `audit_workflow`: corrected workflow and 100-case retrieval evaluation PASS as a harness; the measured recall is still below target and live output is BLOCKED. One pytest function, not 100 extra pytest tests.
- `pool_regression`: one FAIL after adding a no-500 acceptance assertion, confirmed in a fresh ten-request run.
- `security_regressions`: two FAIL (rendered-source citation boundary and HTTP production embedding settings).
- Distinct final checks: 811 = 807 original + four audit functions, with 808 PASS/three FAIL. Recorded invocations including repeats: 814, with 809 PASS/five FAIL. JUnit files `audit-added.xml`, `audit-workflow.xml`, `audit-pool.xml`, `audit-security.xml` retain failed attempts and final probes.

Package-advisory checks reported zero known npm/Python package vulnerabilities. The initial static command checked application/migrations (101 source files checked by mypy). The final `audit_static` command ran full backend Ruff check, format check (162 files) and configured mypy (161 source files), all PASS. The dynamically typed integration audit harness explicitly opts out of strict type checking; unit regressions are typed. There is no whole-project coverage percentage or external penetration-test claim.

## Rerun procedure

Use the existing local development bootstrap in `docs/DEVELOPMENT.md`; provide local test database administration access as that infrastructure requires. Verify `app_env=local` and demo/hash providers first. Existing compose services should be healthy. The commands above are the actual executable recipes; Docker-dependent commands require access to the local Docker engine. Avoid concurrent tests against the same Redis test state.

For a short focused reproduction:

```powershell
docker compose exec -T api pytest tests/unit/audit/test_prompt_evidence.py -q --tb=short
docker compose exec -T -e AUDIT_CONFIRM_POOL=1 api pytest tests/integration/api/audit/test_implementation_audit.py::test_staged_isolated_performance -q --tb=short
docker compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/implementation_audit api pytest tests/integration/api/audit/test_implementation_audit.py::test_business_workflow_and_100_case_evaluation -q --tb=short
corepack pnpm --filter @acs/web exec playwright test --reporter=json
```

The first two commands are expected to fail until application fixes are separately authorized/applied. The complete four-stage workload is selected by omitting AUDIT_CONFIRM_POOL. The API test bind mount includes the dedicated audit tests and dataset; output is written inside the container under `/tmp/implementation_audit`, then copied into `docs/audit/evidence`. Re-running overwrites current per-run fixture outputs; preserve these audit artifacts before comparing later runs. The workflow test's returned local IDs are not stable between runs.

Report tooling: `docs/audit/tools/capture.py` stores redacted command output and metadata; `report.py` renders scores/findings/matrix from the audit rubric; `write_reports.py` renders the remaining reports. Review raw outcomes independently of rendered summaries. The capture wrapper originally encountered a Windows console Unicode print error after saving successful frontend-build and health/RLS command results; those subprocess exit codes and saved logs were zero. Console encoding was corrected. An earlier environment helper attempted unavailable `powershell`; it was corrected to `pwsh` before the actual checks. Neither wrapper issue is counted as an application test failure.

## Preservation and limits

SHA-256 before/after comparison of 242 pre-existing app/configuration files: zero changes (`source_preservation.json`). Only audit reports, tools, dataset and dedicated test additions were authored. Generated build/test outputs and disposable local test data are expected. No production data was touched. No real API keys were copied into evidence. Actual provider and embedding quality, production operations, cloud access policy, repository-history secret scanning and comprehensive penetration testing remain BLOCKED or NOT_TESTED as reported elsewhere.
''')

# A source navigation artifact, not a runtime or dead-code proof.
entrypoints = []
for path in sorted(Path('services/api/app').rglob('*.py')):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    entrypoints.append({'path':path.as_posix(), 'definitions':[{'name':node.name,'line':node.lineno,'kind':type(node).__name__} for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]})
(E / 'python_entrypoints.json').write_text(json.dumps(entrypoints, indent=2), encoding='utf-8')
print('Rendered ten reports; reports 02/05 are rendered by report.py.')
