# Final technical fact check

Covers what the final narration and graphics claim. Claim IDs (F-…) and their evidence links are in
[00_PROJECT_FACT_CHECK.md](00_PROJECT_FACT_CHECK.md).

**How this was checked.** Figures were taken from stored test artifacts and project reports, not
from new test runs. The 439 source files frozen for the final validation run are byte-identical to
the working tree, so those results describe the current code. No test suite was re-run and no real
AI provider was called.

## Figures

| Claim on screen or spoken | Source |
|---|---|
| Self-audit 80.5 → 85.75 of 100, not independent certification | F-68 |
| Seven of seven audit findings pass locally | F-69 |
| 582 backend tests in the first audit, all passing, while added audit checks failed | F-70 |
| Backend 1,209 passed (17 skipped) | F-60 |
| Runtime proxy 17, run separately (the skipped ones, counted once) | F-61 |
| Web unit 243, widget unit 19 (narrated as 262 frontend unit tests) | F-62 |
| Browser journeys 17 | F-63 |
| 1,505 across the listed local suites | F-64 |
| 10 of 10 capacity runs; tightest margin 25 ms | F-65 |
| 100 concurrent: 67 succeeded, 33 controlled rejections, 0 unexpected failures; successful P95 about 1,682 ms | `capacity-100.json` (final run) |
| Loader 5,248 gzip bytes of 10,240 | F-56 |
| Offline answer-bearing Recall@5 68/80 = 85%, target 90% | F-37 |
| Fixes broken on purpose 10 times, all caught | F-67 |
| Backup and restore rehearsal passed; found restored `DELETE` grants | F-66 |

## Behaviour and design

| Claim | Check |
|---|---|
| Modular monolith, several processes; not microservices | F-20, F-21 |
| Server-side sessions; browser holds an opaque identifier in an HttpOnly cookie | F-41; `app/api/cookies.py` read again for this narration |
| Providers: HTTPS, certificate verification, no redirects, environment proxies ignored | `integrations/llm.py` and `rag/embeddings.py` set `verify=True`, `follow_redirects=False`, `trust_env=False`; AUD-03 report |
| Citation provenance, not semantic support | F-36, F-38 |
| Parser containment, not a sandbox | F-53 |
| Recovery about 30 s with shortened test intervals; about 17 minutes by default | AUD-05 report; D04 |
| Recovery ran in under two seconds with ingestion slots busy, at a test interval | Validation results (1.7 s, bound 15 s) |
| One earlier scheduler crash unexplained | Risk register, DEVBEAT-CRASH |
| 159 transport tests; 197 proxy unit cases and 17 runtime checks; 32 citation tests; 100 containment tests; 13 of 20 storage tests failing before; 26 inbox tests | AUD-01…07 and A5.1 reports |
| Widget tested in Chrome only | F-55 |
| AI coding assistants including Codex and Claude Code | Repository traces (fact check §9) |

## Disclosures kept

Deterministic demo model · hash stand-in embeddings · fictional data · local infrastructure · real
model accuracy, semantic quality, faithfulness and citation correctness not established · hosted CI
configured but never run · not deployed · migration recovery policy approval still pending (newest
evidence: `DECISION_REQUIRED`) · analytics figures synthetic · "grounded" means a citation was
stored.

## Deliberately not claimed

No personal task or architectural decision is attributed to you: fact-check items C1–C10 are still
unanswered. No commercial users, production readiness, certification or enterprise security. No
Telegram, WhatsApp or billing. No repository link.

## Illustrative, and labelled as such

The business-problem scene (chapter 1) is labelled "Illustrative". Diagram mechanics are schematic
even where their numbers are measured. D14's third column is labelled "Planned · not built".
