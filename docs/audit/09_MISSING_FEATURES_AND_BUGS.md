# Missing features and bugs

Audit only: no fixes or additional product scope were implemented. Findings are reproduced in report 05 with source locations and regression suggestions.

- **AUD-01 HIGH — Concurrent chat exhausts the database pool before admission control**. FAIL. Authenticated callers can cause request stalls and HTTP 500s; shared per-process pool pressure can degrade other tenants. No cross-tenant data disclosure was observed.
- **AUD-02 MEDIUM — Citation eligibility can include a source absent from the rendered prompt**. FAIL. An answer marker can receive apparently valid provenance for evidence the model never saw. This is not a cross-tenant leak: affected chunks are still tenant-scoped.
- **AUD-03 MEDIUM — Production permits HTTP embedding endpoints**. FAIL. If an operator configures HTTP in production, embedding keys and customer text can travel without TLS. Current local configuration contains no real key; no actual credential disclosure was performed or observed.
- **AUD-04 MEDIUM — Production proxy headers trust every peer**. PARTIALLY_IMPLEMENTED. If the API is reachable outside a strictly trusted proxy boundary, forged forwarded addresses can evade IP limits and distort audit IP metadata. Token/org limits remain independent barriers. Actual public deployment topology was not tested.
- **AUD-05 MEDIUM — Document parser lacks hard worker time/resource isolation**. PARTIALLY_IMPLEMENTED. A pathological but size-compliant document could monopolize ingestion workers or memory. This is a static hardening gap; an exploit PDF/worker kill was not executed.
- **AUD-06 LOW — Conversation inbox still displays a placeholder empty state**. PARTIALLY_IMPLEMENTED. Stored public/widget conversations cannot be reviewed from this inbox despite the implemented API and playground history. Advanced Phase 7 analytics are outside this audit; the present placeholder should be labelled accurately.
- **AUD-07 LOW — Repeated installation has no deduplication or teardown**. PARTIALLY_IMPLEMENTED. Accidental duplicate tags or SPA remounts can create overlapping launchers and extra session issuance. Different-key isolation passed; repeated same-key behavior has only static evidence here.

## Blocked or unverified requirements

- Real provider/semantic embeddings, factual answer quality, faithfulness, semantic citations, appropriate unknown-answer refusal and model-level injection resistance: BLOCKED. No approved live credentials are configured.
- Local retrieval acceptance target: FAIL, 85% versus proposed 90%; genuine semantic-provider results cannot be inferred from the hash baseline.
- Production ingress/proxy trust, secret-manager operations, cloud bucket/IAM policy, public DNS verification, remote CI/deployment, backups/restore and alerts: NOT_TESTED.
- Full WCAG/assistive technology, console-error collection and broad browser/network failure recovery: NOT_TESTED.
- Large-file parser hard CPU/memory/time limits and physical anonymous-message retention purge are not established.
- Strict grounding is effectively always enforced despite appearing configurable; documentation/UI should communicate the supported behavior.

## Placeholder boundaries

The conversation inbox is hardcoded empty, while API persistence and playground history do work. Treat the inbox gap as a UI completeness issue; do not implement advanced Phase 7 analytics during this audit. Demo LLM output is deliberately canned and is not evidence for AI quality. Planned billing/channels/analytics in the draft architecture are outside this Phase 1–6 implementation audit, not automatically defects in the requested current scope.

No confirmed CRITICAL leak was observed. Seven bounded findings include one HIGH; a lack of observed leakage does not eliminate the need for broader production assurance.
