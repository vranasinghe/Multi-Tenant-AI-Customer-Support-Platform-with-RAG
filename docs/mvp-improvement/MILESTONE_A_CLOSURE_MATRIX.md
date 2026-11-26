# Milestone A closure matrix

26 November 2026. "Independent check" = done in this final task: the fix was deliberately broken
in a scratch copy and its tests had to fail
([mutants](evidence/MILESTONE-A-FINAL/verification/)). It was performed by the same engineer who
did the later remediation work, so it is a second method, not a second reviewer.

Source paths are under `services/api/` unless they start with `apps/`. Test counts are from the
final full run ([log](evidence/MILESTONE-A-FINAL/final/backend-full.log),
[JUnit](evidence/MILESTONE-A-FINAL/final/backend-full.xml)).

| | AUD-01 pool starvation | AUD-02 citation provenance | AUD-03 provider transport |
|---|---|---|---|
| Original defect | Ten concurrent chats exhausted the DB pool | A source missing from the prompt could be cited | Production accepted `http` embedding endpoints |
| Original reproduction | 9–10 of 10 HTTP 500, 30 s waits (`docs/audit/05`, `evidence/AUD-01/baseline.log`) | `test_prompt_evidence` failed (`evidence/AUD-02/baseline.log`) | Same file's HTTPS test failed (`evidence/AUD-03/baseline.log`) |
| Implementation | Auth session released before chat work; bounded admission with per-organization waiters; idempotent turn cleanup | Only rendered, authorized sources are citable; one renderer | One canonical URL policy; no redirects; TLS verified; no environment proxies |
| Source | `app/api/deps.py:185`, `app/services/chat_controls.py:116`, `app/services/conversations.py:426` | `app/services/chat_prompt.py:31`, `app/rag/retrieval.py:197`, `:271` | `app/core/provider_urls.py:10`, `app/integrations/llm.py:53`, `app/rag/embeddings.py:130` |
| Regression tests | lifecycle 13, admission 11, turn cleanup 4, capacity 5 | citation and rendered evidence 32, original 2 | transport 159 |
| Runtime evidence | c100: 67 served, 33 rejected, success P95 1,682 ms; 10 of 10 declared runs | All pass in the live stack | Pass, including real TLS handshakes against a synthetic CA |
| Independent check | Holding the auth session again: caught | Making unrendered sources citable: caught | Allowing `http`: 20 failures; following redirects: 15 |
| Limitations | One saturated event loop; latency depends on hardware | Provenance only; semantic correctness unverified | No real provider endpoint exercised |
| Local decision | **PASS** | **PASS** | **PASS** |

| | AUD-04 proxy trust | AUD-05 parser isolation | AUD-06 inbox | AUD-07 widget |
|---|---|---|---|---|
| Original defect | Forwarding headers trusted from every peer | No resource or time limits on parsing | Placeholder inbox (then pagination, truncation, cursor, stale data, mobile gaps) | Repeated install duplicated; no teardown. Later: internal fields public (WIDGET-PRIV-01) |
| Original reproduction | `evidence/AUD-04/baseline-runtime-http.log`; **again here**: all 17 proxy tests fail against an image built from `db4d352` | `evidence/AUD-05/` baseline (52.5 MB allocated before any limit) | `docs/audit/findings.json`; gaps in the AUD-06 report | `evidence/AUD-07/` old-widget browser run |
| Implementation | No peer trusted by default; validated list; launcher passes it explicitly | Limited child per parse, task limits, attempt fencing, publish-by-ownership originals | Scoped cursors, older messages, keyed screens, safe citations | Registry per identity, `destroy`, instance keys, allowlisted public shape |
| Source | `app/core/proxy_trust.py:41`, `app/server.py:19`, `Dockerfile` | `app/rag/parser_process.py:50`, `parser_runner.py:144`, `pipeline.py:139`, `originals.py:59` | `app/services/inbox.py:52`, `:278`, `app/api/conversations.py:137` | `apps/widget/src/lifecycle.ts:55`, `app/services/public_view.py:38` |
| Regression tests | 197 unit, 17 runtime | 100, plus 32 storage and crawl | 26 API, web unit, 4 browser journeys | 9 API, 19 widget unit, 8 browser journeys |
| Runtime evidence | 17 of 17 against the new runtime image | Real prefork workers: limits, loss, restart within the 40 s test bound | Browser journeys pass, desktop and 390 px | 17 of 17 browser journeys |
| Independent check | Trust-all launcher: 37 failures | No memory limit: caught; unfenced publish: caught | Cursor scope removed: caught | Dedup removed: caught; full records returned publicly: caught |
| Limitations | Real ingress and TLS unverified (DEPLOY-01) | **Not a sandbox** (AUD05-SANDBOX); large `.docx` (AUD05-DOCX) | None open beyond product scope | Chrome only; `forget` may time out; error wording |
| Local decision | **PASS** | **PASS** | **PASS** | **PASS** |

## The contract-driven change to `test_citation_provenance.py`

The public stream used to expose `chunk_id`, and the test read it from there. It now:

* asserts `chunk_id` on the **stored** citation (the internal provenance check, unchanged in
  strength: exactly the one rendered chunk);
* asserts the streamed text equals the stored text (unchanged);
* asserts the streamed citations equal the stored ones for the dashboard path, and their public
  projection for the widget path.

The expected public value is computed with the production `public_citation`, so by itself this
test would not notice that function leaking a field. `test_widget_public_privacy.py` checks the
exact public keys independently, and the "full records returned publicly" mutation was caught.
No authorization assertion changed. **Accepted: not a weakening.**

## `destroy({forget: true})`

Confirmed success (the frame answers `acs-forgotten`) means the resume entry was deleted. After 5
seconds without an answer the frame is removed anyway and the entry **may remain**; the caller
gets `true` either way. Now stated in `docs/WIDGET_DEPLOYMENT.md`; registered as WIDGET-FORGET.
Behaviour unchanged.

## Observation about tests

`lifecycle.test.ts` was written together with its implementation (AUD-07), not seen failing first;
the dedup mutation above now shows it detects that defect. The AUD-07 report's "destroy while
loading … (unit and browser)" rests on unit tests and quick stand-in-frame browser cycles: no
browser test delays bootstrap or history and then destroys, and blocked-frame and 401/403/429/5xx
widget states have no browser coverage.
