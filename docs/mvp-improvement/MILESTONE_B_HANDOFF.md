# Milestone B handoff — real provider execution (not started)

Nothing here has run against a paid provider. **Every provider call needs your explicit
authorization**, with a spending limit.

## What exists

| Area | Source | State |
|---|---|---|
| Chat adapter | `services/api/app/integrations/llm.py`: OpenAI-compatible streaming, no redirects, TLS verified, no environment proxies, bounded retries on 429/502/503/504, usage requested | Tested against loopback and mock transports only |
| Embedding adapter | `services/api/app/rag/embeddings.py`: OpenAI-compatible, 1536 dimensions requested, bounded response | Same |
| Endpoint policy | `app/core/provider_urls.py`; `LLM_BASE_URL`, `EMBEDDING_BASE_URL` must be HTTPS | Tested |
| Offline providers | `LLM_PROVIDER=demo`, `EMBEDDING_PROVIDER=hash` (`hash-v1`) | Lexical only; refused in production |
| Cost controls | `CHAT_MONTHLY_TOKEN_LIMIT`, `CHAT_MONTHLY_COST_LIMIT_USD`, `CHAT_MODEL_PRICES`, per-organization rate and concurrency limits, usage reservations | Prices are operator estimates; a model without a price must be checked before enabling |
| Gemini switch | `scripts/enable-gemini.ps1`: prompts for a key, writes `.env`, **recreates containers** | Not run in this work; do not run it casually |

## Configuration facts to resolve first

* The vector column is `vector(1536)`. A model must produce 1536 dimensions or needs a migration.
* Changing the embedding model requires re-indexing every document; vectors from different models
  must not be mixed (chunks record `embedding_model`).
* The developer `.env` contains real keys. Use a separate, disposable stack and a separate key with
  a hard provider-side spending limit.
* `CHAT_MIN_VECTOR_SCORE=0.15` was chosen with the hash baseline and must be re-tuned.

## Known RAG evaluation limits

* Audit set: `docs/audit/rag_evaluation_dataset.jsonl`, 100 synthetic cases, twenty fictional
  documents. Not a customer-domain benchmark; labels are phrase matches.
* Recall@5 with the offline baseline is **85%**, below the proposed 90%. Paraphrase is weakest
  (12/20). This predicts nothing about a real model.
* `docs/RAG_EVALUATION.md` reports a second, smaller harness (25 answerable questions): hybrid did
  not beat vector-only there; that too is lexical.
* Not measured at all: correctness, faithfulness, refusal of unanswerable questions, whether a
  cited source supports the sentence, prompt-injection resistance, other languages, tables/OCR,
  long documents, follow-up rewriting in the real conversation engine.
* Citation **provenance** is enforced (only rendered, authorized sources can be cited). Citation
  **correctness** is not.

## Authorizations needed before B starts

1. Provider and models (chat and embedding).
2. A dedicated key, supplied by you into a local secret file, never in chat or the repository.
3. A spending cap for the evaluation, and permission to re-index a synthetic corpus.
4. Whether any real customer content may ever be sent (recommended: no).
5. Acceptance targets (J3): Recall@5, faithfulness, refusal and citation-support thresholds, set
   **before** running.

## Suggested first steps once authorized

Transport contract run against the real endpoint (streaming, usage, errors, timeouts); price table
check; re-index the synthetic corpus; repeat the 100-case protocol; manual judgement of answers and
citations; record cost and latency. Keep deterministic CI offline.
