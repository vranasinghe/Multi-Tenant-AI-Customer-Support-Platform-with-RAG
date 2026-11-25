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
