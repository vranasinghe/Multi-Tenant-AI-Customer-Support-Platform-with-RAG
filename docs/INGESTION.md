# Document & website ingestion, indexing and retrieval

| Field | Value |
|---|---|
| Status | Implemented (2026-11-22) |
| Code | `services/api/app/rag/`, `app/services/knowledge/`, `app/api/knowledge.py`, `app/workers/tasks/ingest.py`, migration `0004` |
| Related | [API_SPEC §2.4](API_SPEC.md) · [DATABASE §3.4](DATABASE.md) · [SECURITY §7, §10](SECURITY.md) · [RAG_EVALUATION](RAG_EVALUATION.md) |

## 1. Flow

```
upload (raw body) ─► validate extension + type + signature ─► private object storage
        │                                                         │
        ▼                                                         ▼
documents + ingestion_jobs rows (one transaction) ─► Celery `ingest.process_document`
                                                                  │
 claim job (compare-and-set) ► read original ► extract ► normalize ► dedupe ► chunk ► embed (batched)
                                                                  │
                          one transaction: insert chunks(v+1) · delete old versions · document ready · job succeeded
```

Website sources use `ingest.crawl_source`: robots.txt → bounded BFS through `SafeFetcher` → main-content extraction → per page the same dedupe/chunk/embed/publish path. Unchanged pages (same content hash and embedding model) are skipped, so a re-sync only re-embeds what changed.

Statuses: documents `queued → processing → ready | failed`; jobs `queued → processing → succeeded | failed`. Errors carry a stable `error_code` (`unsupported_type`, `corrupt`, `encrypted`, `no_text`, `too_large`, `too_many_pages`, `duplicate_content`, `embedding_failed`, `storage_error`, `blocked_destination`, `fetch_failed`…) and a user-safe message. Failed documents can be retried (`POST …/documents/{id}/reprocess`).

## 2. Security properties (and where they are tested)

| Property | Mechanism | Tests |
|---|---|---|
| File type is decided by content | extension ∧ declared MIME ∧ magic bytes must agree; OOXML must be a plain `.docx` (macros/templates refused); OLE (encrypted) → `encrypted` | `unit/rag/test_files.py`, `test_knowledge_documents.py` |
| Decompression/parse bombs | zip entry count, size and ratio caps, member reads capped, `defusedxml` (no entity expansion), PDF page and text caps | `unit/rag/test_extract.py` |
| Private storage | bucket has public access blocked; no object URL is ever given to a browser; keys are server-generated UUID paths (filenames never reach keys); workers/purger refuse keys outside `orgs/{org}/` | `test_workers_refuse_storage_keys…`, `test_storage_purge_retries…` |
| SSRF | http(s) only, no credentials, ports 80/443, every resolved address must be globally routable (loopback, RFC1918, link-local/cloud metadata, CGNAT, multicast, IPv4-mapped/6to4/Teredo/NAT64 all refused); **connect to the validated IP** (rebinding-safe, TLS SNI preserved); manual redirects re-validated per hop; size/time/redirect caps; `Accept-Encoding: identity` | `unit/rag/test_safe_fetch.py`, `test_knowledge_websites.py` |
| Site authorization | creating a website source requires an explicit "I may crawl this site" confirmation, recorded in the source config | `test_source_validation` |
| Tenant isolation | `org_id` + `chatbot_id` filtered in every SQL query **and** RLS on all new tables; composite FKs; workers set the tenant GUC from the job payload; retrieval joins the live chatbot | `rag_eval`, `test_sql_filters_hide_deleted_chatbots_and_foreign_tenants`, existing isolation sweeps |
| Deletion | document/source delete removes chunks, vectors and jobs in the same transaction; the original is removed via an outbox (`storage_deletions`) so a crash cannot orphan it | `test_delete_removes_chunks…`, live test |
| Untrusted text | extracted text is data; rendered with `<`, `>`, `&`, quotes escaped inside delimited blocks; retrieved text is never placed in the system message; UI shows passages as plain text | `unit/rag/test_prompt_safety.py`, `rag_eval` injection test, `knowledge.test.tsx` |
| No sensitive logging | logs carry ids, stages, counts and error codes only; error details are our own strings (never document text) | `test_logs_never_contain_document_text…` |

## 3. Reliability

* **No duplicate processing**: claim is a compare-and-set; a partial unique index allows one active job per document and per crawl source; concurrent workers → exactly one wins (tested with 6 threads).
* **Retries**: transient failures (embedding provider 429/5xx/timeouts, storage or DB hiccups, DNS `EAI_AGAIN`, HTTP 429/5xx) re-queue the job and retry with exponential backoff (`INGEST_RETRY_BASE_SECONDS`·2ⁿ, capped, ±20% jitter) up to `INGEST_MAX_ATTEMPTS`; permanent failures (corrupt, no text, blocked destination…) are never retried automatically.
* **Safe to retry**: chunks are only visible after the atomic publish; a failed or retried attempt leaves the previous version intact. A failed *re*processing keeps serving the last published version.
* **Recovery**: `ingest.sweep` (Celery beat, every 2 min) re-publishes jobs whose broker message was lost (queued > 2 min), resets jobs whose worker died (stale heartbeat), fails jobs that already used all attempts, and finishes pending storage deletions. It discovers work through two narrow `SECURITY DEFINER` functions (no BYPASSRLS role) and acts inside each organization's own context.

## 4. Retrieval

* Vector (pgvector cosine, HNSW) and keyword (Postgres FTS, OR-query over content words, operators impossible by construction) retrieval; hybrid fuses both with Reciprocal Rank Fusion (k = 60). Deterministic tie-breaking (URI, ordinal).
* Only chunks of a document's **current published version** with the **current embedding model** are searched. Changing `EMBEDDING_MODEL` makes older documents invisible to search (never compared across vector spaces) and flags them `needs_reindex`; `POST …/reindex` re-processes them from the stored originals (`?force=true` re-processes everything).
* Optional relevance gate: `RETRIEVAL_MIN_VECTOR_SCORE` (off by default; see the evaluation for the measured trade-off).
* `POST …/retrieval/search` (permission `chatbot:test`) is a debugger: it returns passages and scores, no generation.

## 5. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `STORAGE_BACKEND`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | `s3`, – , `acs-documents`, – | Private object storage (RustFS locally via Compose; any S3 API in production). `memory` is for tests and refused in production |
| `UPLOAD_MAX_BYTES` | 25 MiB | Per-file limit (413 beyond; also enforced while streaming) |
| `MAX_DOCUMENTS_PER_CHATBOT`, `ORG_STORAGE_LIMIT_BYTES` | 500, 2 GiB | Static limits until plans ship (402 `plan_limit_reached`) |
| `EXTRACT_MAX_PAGES`, `EXTRACT_MAX_CHARS`, `DOCX_MAX_UNCOMPRESSED_BYTES` | 500, 5 M, 100 MiB | Extraction guards |
| `CHUNK_SIZE_TOKENS`, `CHUNK_OVERLAP_TOKENS` | 350, 50 | Chunking (tokens ≈ characters / 4) |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_BATCH_SIZE` | `hash`, `hash-v1`, OpenAI URL, –, 64 | `hash` is a **local development baseline** and is refused in production; `openai_compatible` calls any `/embeddings` endpoint. Dimensions are fixed at 1536 (column width) |
| `INGEST_MAX_ATTEMPTS`, `INGEST_RETRY_BASE_SECONDS`, `INGEST_RETRY_MAX_SECONDS`, `INGEST_STUCK_AFTER_SECONDS` | 4, 5, 300, 900 | Retry policy and stuck-job threshold |
| `CRAWL_MAX_PAGES_LIMIT`, `CRAWL_MAX_DEPTH_LIMIT`, `CRAWL_DELAY_SECONDS`, `FETCH_*` | 200, 5, 0.5 s, 10 s / 20 s / 5 MiB / 5 redirects | Crawl bounds |
| `RATE_LIMIT_UPLOAD_PER_MINUTE`, `RATE_LIMIT_SEARCH_PER_MINUTE` | 60 | Per organization / per user |

## 6. Known limitations

* Scanned documents are not OCR'd (they fail with `no_text`). Tables in PDFs are extracted as plain text; DOCX tables as `a | b` rows.
* Token counts are estimates; the default embedder is a lexical baseline — **use a real embedding model before relying on retrieval quality**.
* Crawling is same-host only, HTML only, no JavaScript rendering, no sitemap parsing; pages that disappear are reported (`not_seen`) but not auto-deleted.
* A document being reindexed after an *embedding model* change is not searchable until it is republished (old and new vectors are never mixed).
* Duplicate detection by normalized text hash catches identical text across formats, not near-duplicates.
* Postgres/`pgvector` HNSW with selective filters relies on iterative scans (`hnsw.iterative_scan`); very large tenants may need partitioning or per-tenant indexes later.
* Chatbot deletion is a soft delete: its chunks stay in the table (hidden from retrieval) until the purge job planned for the undo window.


## Provider transport security (AUD-03)

Embedding requests use the installed synchronous httpx2 client with certificate verification,
redirects disabled and environment proxies/trust overrides disabled. API and worker startup
apply the same endpoint policy. Model IDs, dimensions, batching and ordering are unchanged;
no reindex is needed solely for this transport change. HTTP 429/5xx and connection/TLS/read
failures retain transient `embedding_failed` classification; other non-2xx statuses, including
all redirects, are permanent failures. Provider bodies and exception chains are not logged.
Malformed JSON retains its previous transient classification; malformed/incorrectly shaped
vectors remain permanent. No new retry loop is added: existing ingestion retries remain in charge.

The configured embedding timeout bounds connect/read/write/pool operations (connect additionally
capped at five seconds). Each response read checks a monotonic request deadline and a 32 MiB
response ceiling. A currently blocked read can add up to one read-timeout interval beyond that
deadline; this is not a hard worker execution deadline. Each batch has its own request budget.
The query subprocess keeps AUD-01's independent hard wall watchdog and parent cancellation/kill/reap.
Worker/parser hard resource isolation remains AUD-05, outside this change.

Only `APP_ENV=local|test` plus explicit `ALLOW_INSECURE_LOCAL_PROVIDERS=true` permits HTTP,
and only for localhost, canonical IPv4 loopback or IPv6 ::1. Container hostnames and LAN addresses
are not HTTP exceptions. See DEVELOPMENT.md section 9 for operator migration guidance and limits.
