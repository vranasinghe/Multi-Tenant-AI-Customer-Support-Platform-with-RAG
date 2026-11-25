# Phase implementation matrix

Verified score: **80.5/100**. Ten equally weighted rubric items per phase. PASS earns full item weight; PARTIALLY_IMPLEMENTED earns half only for the explicitly verified subpart. FAIL, BLOCKED, NOT_TESTED and NOT_IMPLEMENTED earn zero. The score does not override release blockers.

Phase numbering follows the pasted guide, not the repository roadmap (which starts foundations at Phase 0).

| ID | Requirement / actual source | Evidence kind and record | Status | Severity | Score | Action |
|---|---|---|---|---|---|---|
| P1-01 | Repository and architecture — `package.json; services/api/pyproject.toml; docs/ARCHITECTURE.md` | static: Static inspection; source_inventory_before.json | PASS | INFORMATIONAL | 1/1 | Keep layer-first modular monolith |
| P1-02 | Pinned dependency build — `services/api/uv.lock; pnpm-lock.yaml` | runtime: evidence/backend_build.log; frontend_build.log | PASS | INFORMATIONAL | 1/1 | Keep locked builds |
| P1-03 | Environment safety — `services/api/app/core/config.py:265` | runtime: evidence/security_regressions.log | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.5/1 | Require HTTPS embeddings (AUD-03) |
| P1-04 | Docker production artifacts — `services/api/Dockerfile; apps/web/Dockerfile` | runtime: evidence/backend_build.log; frontend_build.log | PASS | INFORMATIONAL | 1/1 | Retain tested images |
| P1-05 | Schema constraints/migrations — `services/api/migrations/versions` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 1/1 | Keep isolated rollback test |
| P1-06 | Database/Redis/worker health — `scripts/smoke.mjs` | runtime: evidence/health_rls.log | PASS | INFORMATIONAL | 1/1 | Add storage/provider-specific readiness |
| P1-07 | CI and deployment automation — `.github/workflows/ci.yml` | static: Static inspection; source_inventory_before.json | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.5/1 | Local equivalents pass; remote CI/CD unverified |
| P1-08 | Errors and logging — `services/api/app/core/errors.py; services/api/app/core/request_context.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 1/1 | Keep no-content logging tests |
| P1-09 | Secret management boundary — `.env.example; services/api/app/core/config.py` | static: Static inspection; environment.log | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.5/1 | Server-only keys verified; external secret manager/history not verified |
| P1-10 | Production operations/restore — `docs/ROADMAP.md` | blocked: Static inspection; environment.log | NOT_TESTED | INFORMATIONAL | 0/1 | Run backups, restore, alerts and deployment drills |
| P2-01 | Registration/verification — `services/api/app/services/identity/auth.py` | runtime: evidence/baseline_backend.log; business_workflow.json | PASS | INFORMATIONAL | 2/2 | Keep tests |
| P2-02 | Login/logout — `services/api/app/services/identity/auth.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep tests |
| P2-03 | Password reset/token reuse — `services/api/app/services/identity/tokens.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep tests |
| P2-04 | Session expiry/revocation — `services/api/app/services/identity/sessions.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep tests |
| P2-05 | Organizations and memberships — `services/api/app/services/tenancy` | runtime: evidence/baseline_backend.log; business_workflow.json | PASS | INFORMATIONAL | 2/2 | Keep tests |
| P2-06 | RBAC and privilege changes — `services/api/app/services/tenancy/policy.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep permission sweep |
| P2-07 | IDOR and manipulated IDs — `services/api/app/api/deps.py:122` | runtime: evidence/business_workflow.json | PASS | INFORMATIONAL | 2/2 | Keep two-org cases |
| P2-08 | Database FORCE RLS — `services/api/app/core/rls.py` | runtime: evidence/health_rls.log; baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep runtime role unprivileged |
| P2-09 | Tenant file-key scoping — `services/api/app/rag/storage.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Audit deployment bucket/IAM separately |
| P2-10 | Tenant/chatbot vector scoping — `services/api/app/rag/retrieval.py` | runtime: evidence/rag_metrics.json; baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Maintain filters and RLS |
| P3-01 | Navigation/routes — `apps/web/src/components/app-shell.tsx` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1/1 | Keep browser checks |
| P3-02 | Chatbot create — `apps/web/src/components/chatbots/chatbot-wizard.tsx` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1/1 | Keep checks |
| P3-03 | Chatbot listing — `apps/web/src/components/chatbots/chatbot-list.tsx` | runtime: evidence/frontend_tests.log | PASS | INFORMATIONAL | 1/1 | Keep checks |
| P3-04 | Chatbot update/persistence — `apps/web/src/components/chatbots/chatbot-editor.tsx` | runtime: evidence/frontend_tests.log; business_workflow.json | PASS | INFORMATIONAL | 1/1 | Keep checks |
| P3-05 | Chatbot delete — `services/api/app/services/chatbots/service.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 1/1 | Keep checks |
| P3-06 | Branding/settings — `apps/web/src/components/chatbots/config-fields.tsx` | runtime: evidence/browser.log; business_workflow.json | PASS | INFORMATIONAL | 1/1 | Clarify strict_grounding always-on policy |
| P3-07 | Knowledge management/API — `apps/web/src/components/knowledge` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1/1 | Keep checks |
| P3-08 | Loading/errors/forms — `apps/web/src/components/kit; apps/web/src/lib/api` | runtime: evidence/frontend_tests.log | PASS | INFORMATIONAL | 1/1 | Broaden live fault injection |
| P3-09 | Responsive/accessibility basics — `apps/web/src/components/chatbots; apps/widget/src/panel.ts` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1/1 | Keyboard/mobile verified; full WCAG audit not claimed |
| P3-10 | Conversation screen real data — `apps/web/src/components/conversations/conversations-screen.tsx:61` | static: Static inspection; source_inventory_before.json | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.5/1 | Resolve AUD-06 |
| P4-01 | PDF/DOCX extraction — `services/api/app/rag/extract.py` | runtime: evidence/baseline_backend.log; business_workflow.json | PASS | INFORMATIONAL | 2.5/2.5 | Add constrained parser deadlines |
| P4-02 | Website ingestion/SSRF — `services/api/app/rag/safe_fetch.py; services/api/app/rag/crawler.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2.5/2.5 | Fixture network verified; public customer sites untested |
| P4-03 | Invalid/corrupt/empty/limits — `services/api/app/rag/files.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2.5/2.5 | Keep malformed fixtures |
| P4-04 | Duplicate/reindex/versioning — `services/api/app/rag/pipeline.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2.5/2.5 | Keep version-scoped retrieval |
| P4-05 | Jobs/retries/states — `services/api/app/rag/pipeline.py; services/api/app/workers` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2.5/2.5 | Add worker resource isolation |
| P4-06 | Stored chunks/dimensions/index — `services/api/migrations/versions/20261122_0004_knowledge_and_rag.py` | runtime: evidence/business_workflow.json | PASS | INFORMATIONAL | 2.5/2.5 | 1536-dimensional stored vectors verified |
| P4-07 | Tenant/chatbot filters — `services/api/app/rag/retrieval.py:70` | runtime: evidence/rag_metrics.json | PASS | INFORMATIONAL | 2.5/2.5 | Zero leaks in measured searches |
| P4-08 | Deletion/no stale retrieval — `services/api/app/services/knowledge/service.py` | runtime: evidence/business_workflow.json; baseline_backend.log | PASS | INFORMATIONAL | 2.5/2.5 | Keep deletion regression |
| P4-09 | Real semantic embedding integration — `services/api/app/rag/embeddings.py` | blocked: Static inspection; environment.log | BLOCKED | INFORMATIONAL | 0/2.5 | Supply approved provider/model and reindex |
| P4-10 | Recall@5 at proposed 90% target — `services/api/tests/integration/api/audit/dataset.json` | runtime: evidence/rag_metrics.json | FAIL | MEDIUM | 0/2.5 | Measured local lexical baseline 85%; real model quality blocked |
| P5-01 | Conversation authorization/API — `services/api/app/api/conversations.py` | runtime: evidence/baseline_backend.log; business_workflow.json | PASS | INFORMATIONAL | 2/2 | Keep IDOR checks |
| P5-02 | Message/history persistence — `services/api/app/services/conversations.py` | runtime: evidence/business_workflow.json | PASS | INFORMATIONAL | 2/2 | Keep persisted-state assertions |
| P5-03 | SSE/errors/cancel/timeouts — `services/api/app/api/conversations.py; services/api/app/integrations/llm.py` | runtime: evidence/baseline_backend.log; browser.log | PASS | INFORMATIONAL | 2/2 | Real transport contract still needs provider run |
| P5-04 | Prompt injection resistance — `services/api/app/services/chat_prompt.py` | runtime: evidence/baseline_backend.log | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 1/2 | Structural escaping verified; real model resistance blocked |
| P5-05 | Live configured LLM generation — `services/api/app/integrations/llm.py:121` | blocked: Static inspection; environment.log | BLOCKED | INFORMATIONAL | 0/2 | Demo is a canned response |
| P5-06 | Factual/paraphrase/complex quality — `docs/audit/rag_evaluation_dataset.jsonl` | blocked: Static inspection; rag_results.json | BLOCKED | INFORMATIONAL | 0/2 | Run 100 cases with real model and manual judgments |
| P5-07 | Context-aware conversation — `services/api/app/services/conversations.py` | runtime: evidence/baseline_backend.log | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 1/2 | Mock history verified; semantic follow-up answers blocked |
| P5-08 | Citation correctness/provenance — `services/api/app/services/chat_prompt.py:51` | runtime: evidence/security_regressions.log | FAIL | MEDIUM | 0/2 | Fix AUD-02 and evaluate semantic attribution |
| P5-09 | Token/rate/cost limits — `services/api/app/services/chat_controls.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 2/2 | Keep reservations and independent limits |
| P5-10 | Concurrent request safety — `services/api/app/api/deps.py:62` | runtime: evidence/performance.json; pool_regression.log | FAIL | HIGH | 0/2 | Fix AUD-01 before MVP |
| P6-01 | Versioned install script — `apps/widget/src/loader.ts; services/api/widget_assets/v1/manifest.json` | runtime: evidence/browser.log; frontend_build.log | PASS | INFORMATIONAL | 1.5/1.5 | Keep build-before-API ordering |
| P6-02 | Launcher/open/close — `apps/widget/src/panel.ts` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1.5/1.5 | Keep user-visible unavailable state improvements |
| P6-03 | Streaming/source display — `apps/widget/src/panel.ts` | runtime: evidence/browser.log; security_regressions.log | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.75/1.5 | Display works; provenance correctness has AUD-02 |
| P6-04 | Saved branding/live preview — `apps/web/src/components/chatbots/widget-install.tsx` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1.5/1.5 | Keep real frame preview |
| P6-05 | Mobile/CSS isolation — `apps/widget/src/loader.ts; apps/widget/src/panel.ts` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1.5/1.5 | Browser fixture verified |
| P6-06 | Keyboard/focus basics — `apps/widget/src/panel.ts` | runtime: evidence/browser.log | PASS | INFORMATIONAL | 1.5/1.5 | Full assistive-technology audit untested |
| P6-07 | Anonymous resume/retention access — `services/api/app/services/widget_chat.py` | runtime: evidence/baseline_backend.log; browser.log | PASS | INFORMATIONAL | 1.5/1.5 | Database purge is separate and absent |
| P6-08 | Verified origin/domain controls — `services/api/app/services/widget_domains.py` | runtime: evidence/baseline_backend.log | PASS | INFORMATIONAL | 1.5/1.5 | DNS mocked in automated tests; manual seven-day renewal |
| P6-09 | Public permissions/multiple bots/XSS — `services/api/app/api/widget_chat.py; apps/widget/src/panel.ts` | runtime: evidence/browser.log; baseline_backend.log | PASS | INFORMATIONAL | 1.5/1.5 | No secret/admin privilege in public IDs |
| P6-10 | Duplicate init/network recovery breadth — `apps/widget/src/loader.ts:41` | static: Static inspection; source_inventory_before.json | PARTIALLY_IMPLEMENTED | INFORMATIONAL | 0.75/1.5 | No dedup; real DNS/browser outage permutations NOT_TESTED |

Runtime-exercised coverage: 51/60 rows; static-only: 5/60; blocked/untested: 4/60. Runtime-exercised includes failed checks and partially verified behavior; it is not a pass percentage.

Status vocabulary: PASS, FAIL, PARTIALLY_IMPLEMENTED, NOT_IMPLEMENTED, NOT_TESTED, BLOCKED, NOT_APPLICABLE. Each evidence item is scoped to the stated test model/environment. Baseline green tests do not establish factual AI answer quality.
