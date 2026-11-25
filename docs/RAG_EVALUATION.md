# RAG evaluation — measured results and their limits

| Field | Value |
|---|---|
| Date | 2026-11-22 |
| Harness | `services/api/tests/integration/api/rag_eval/` (`pytest -m integration -k rag_eval`) |
| Baseline | `rag_eval/baseline.json` — committed; CI fails if Recall@5 or MRR@10 drop more than 0.04 below it |
| Reproduce | `docker compose exec api pytest tests/integration/api/rag_eval -m integration -s` (prints `RAG_EVAL_REPORT {...}`; set `RAG_EVAL_REPORT=<path>` to write JSON) |

## What was measured

Everything runs through the **real path**: file upload → Celery job logic → extraction → chunking → embeddings → pgvector/FTS → `POST …/retrieval/search`. Runs are deterministic (verified: three consecutive runs produced byte-identical reports).

* **Embedder: `hash-v1`** — an offline, deterministic *feature-hashing* embedder (words + word pairs, light stemming, stop-words removed). It has **no semantic knowledge**: similarity means shared vocabulary. It exists so the pipeline and CI work without an API key. **No result below says anything about a real embedding model.**
* **Corpus**: 8 short help-center documents of a fictional retailer, chunked at 60 tokens with 10 overlap (deliberately small so documents split into several chunks).
* **Questions**: 25 answerable (10 `overlap` = shares most words with the answer, 10 `paraphrase`, 5 `synonym` = almost no shared words) and 10 unanswerable. Relevance is chunk-level: a retrieved chunk is relevant if it contains the question's gold answer phrase.
* **Metrics**: Recall@K (≥1 relevant chunk in the top K) and MRR@10, K ∈ {1, 3, 5}.

## Results (25 answerable questions, top-10 retrieved)

| Method | Recall@1 | Recall@3 | Recall@5 | MRR@10 |
|---|---|---|---|---|
| Vector only | 0.68 | 0.80 | 0.88 | 0.751 |
| Keyword only (FTS) | 0.64 | 0.72 | 0.76 | 0.683 |
| Hybrid (RRF of both) | 0.64 | 0.76 | 0.88 | 0.728 |

Recall@5 by question type:

| Method | overlap (10) | paraphrase (10) | synonym (5) |
|---|---|---|---|
| Vector only | 1.00 | 0.90 | 0.60 |
| Keyword only | 1.00 | 0.80 | 0.20 |
| Hybrid | 1.00 | 0.90 | 0.60 |

### Findings

1. **Hybrid did not beat vector-only on this set.** Recall@5 is equal (0.88) and hybrid is slightly lower on Recall@1/3 and MRR. This is expected here: the stand-in embedder is itself lexical, so keyword search adds little that vector search lacks. With a real semantic embedder the trade-off could differ; **that has not been measured**, so hybrid remains the default on design grounds (exact-term matching for SKUs, error codes, names), not on evidence. Re-run this harness with the production embedder before relying on it.
2. **Questions with little shared vocabulary are hard** (synonym Recall@5 = 0.60 vector/hybrid, 0.20 keyword). Only a semantic embedder can address that; 5 questions are too few for precise numbers.
3. **Hostile documents cost a little.** Adding a keyword-stuffing page and a prompt-injection page to the same chatbot lowered Recall@5 from 0.88 to 0.84 (vector, hybrid) and from 0.76 to 0.68 (keyword); Recall@1 for hybrid fell from 0.64 to 0.60. One question's worth of movement on 25 questions — directionally real, statistically weak.
4. **Irrelevant questions are only handled if the relevance gate is on.** Without it, every unanswerable question still returned chunks (false-accept 1.00 on the 5 test questions). A cosine-similarity threshold of **0.148**, chosen on the 5 *dev* unanswerable questions only, gave a test false-accept rate of **0.00** — at the cost of Recall@5 on the 12 *test* answerable questions dropping from **1.00 to 0.75**. The gate is therefore **off by default** (`RETRIEVAL_MIN_VECTOR_SCORE=0`); the right threshold depends on the embedder and must be re-calibrated per model.

## Security and robustness checks in the same harness (invariants, always asserted)

| Check | Result |
|---|---|
| Cross-tenant leakage: 35 questions × 3 methods × 2 tenants = 210 searches (> 500 returned chunks), including a byte-identical document in both tenants (identical embeddings) and contradictory facts | **0 leaked results**; each tenant only ever sees its own facts |
| Duplicates: same bytes uploaded twice | rejected at upload (409) |
| Duplicates: same text as a different file type | ingested then marked `duplicate_content`, never retrievable |
| Malformed: empty text file, corrupt PDF, scanned (no-text) PDF | fail with `no_text` / `corrupt` / `no_text`, never retrievable |
| Prompt injection inside a source document | retrievable *as data*, but escaped and delimited: cannot close our tags, forge a system turn or reach the system message |

## What this evaluation does not show

* Nothing about answer quality: no LLM generation is evaluated (generation is a later phase).
* Nothing about a real embedding model, other languages, long documents, tables/OCR, or real customer content.
* 25 + 10 questions from one fictional domain: differences of one or two questions are noise. Treat the numbers as a **regression guard and sanity check**, not a benchmark.
* The relevance threshold and hybrid weighting were not tuned beyond what is reported; no quality improvement is claimed.

## Next steps (not done)

Run the same harness with the production embedding model; grow the dataset (≥ 100 questions, several corpora, ≥ 20 must-refuse per the roadmap); add generation-level faithfulness/refusal metrics when chat ships.
