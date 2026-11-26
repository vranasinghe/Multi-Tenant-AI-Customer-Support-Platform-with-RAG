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
   one heavy job per org             (parser child process)
                                                                  │
                          one transaction: insert chunks(v+1) · delete old versions · document ready · job succeeded
```

Website sources use `ingest.crawl_source`: robots.txt → bounded BFS through `SafeFetcher` → main-content extraction → per page the same dedupe/chunk/embed/publish path. Unchanged pages (same content hash and embedding model) are skipped, so a re-sync only re-embeds what changed.

Statuses: documents `queued → processing → ready | failed`; jobs `queued → processing → succeeded | failed`. Errors carry a stable `error_code` (`unsupported_type`, `corrupt`, `encrypted`, `no_text`, `too_large`, `too_many_pages`, `duplicate_content`, `embedding_failed`, `storage_error`, `blocked_destination`, `fetch_failed`, `parse_timeout`, `parse_resource_limit`, `parse_invalid_output`, `task_timeout`…) and a user-safe message. Failed documents can be retried (`POST …/documents/{id}/reprocess`).

## 2. Security properties (and where they are tested)

| Property | Mechanism | Tests |
|---|---|---|
| File type is decided by content | extension ∧ declared MIME ∧ magic bytes must agree; OOXML must be a plain `.docx` (macros/templates refused); OLE (encrypted) → `encrypted` | `unit/rag/test_files.py`, `test_knowledge_documents.py` |
| Decompression/parse bombs | zip entry count, size and ratio caps, member reads capped, `defusedxml` (no entity expansion), PDF page and text caps; every parse in a limited child process (§7) | `unit/rag/test_extract.py`, `unit/mvp_improvement/test_parser_runner.py` |
| Private storage | bucket has public access blocked; no object URL is ever given to a browser; keys are server-generated UUID paths (filenames never reach keys); workers/purger refuse keys outside `orgs/{org}/`; an object is written once, never overwritten (§9) | `test_workers_refuse_storage_keys…`, `test_storage_purge_retries…` |
| SSRF | http(s) only, no credentials, ports 80/443, every resolved address must be globally routable (loopback, RFC1918, link-local/cloud metadata, CGNAT, multicast, IPv4-mapped/6to4/Teredo/NAT64 all refused); **connect to the validated IP** (rebinding-safe, TLS SNI preserved); manual redirects re-validated per hop; size/time/redirect caps; `Accept-Encoding: identity` | `unit/rag/test_safe_fetch.py`, `test_knowledge_websites.py` |
| Site authorization | creating a website source requires an explicit "I may crawl this site" confirmation, recorded in the source config | `test_source_validation` |
| Tenant isolation | `org_id` + `chatbot_id` filtered in every SQL query **and** RLS on all new tables; composite FKs; workers set the tenant GUC from the job payload; retrieval joins the live chatbot | `rag_eval`, `test_sql_filters_hide_deleted_chatbots_and_foreign_tenants`, existing isolation sweeps |
| Deletion | document/source delete removes chunks, vectors and jobs in the same transaction; the original is removed via an outbox (`storage_deletions`) so a crash cannot orphan it | `test_delete_removes_chunks…`, live test, `test_original_ownership.py` |
| Untrusted text | extracted text is data; rendered with `<`, `>`, `&`, quotes escaped inside delimited blocks; retrieved text is never placed in the system message; UI shows passages as plain text | `unit/rag/test_prompt_safety.py`, `rag_eval` injection test, `knowledge.test.tsx` |
| No sensitive logging | logs carry ids, stages, counts and error codes only; error details are our own strings (never document text) | `test_logs_never_contain_document_text…` |

## 3. Reliability

* **No duplicate processing**: claim is a compare-and-set; a partial unique index allows one active job per document and per crawl source; concurrent workers → exactly one wins (tested with 6 threads).
* **Attempt fencing**: `ingestion_jobs.attempt` only grows, on claim. Heartbeat, publish, fail, re-queue and every crawl write require `status = 'processing' AND attempt = <mine>`, checked with the row locked where something is written. A worker that was reset by the sweeper, superseded, or whose document was deleted changes nothing (`stale` / `gone`). Lock order is source → document → job everywhere that takes more than one.
* **Retries**: transient failures (embedding provider 429/5xx/timeouts, storage or DB hiccups, DNS `EAI_AGAIN`, HTTP 429/5xx, task soft time limit, a parser killed from outside or unable to start) re-queue the job and retry with exponential backoff (`INGEST_RETRY_BASE_SECONDS`·2ⁿ, capped, ±20% jitter) up to `INGEST_MAX_ATTEMPTS`; permanent failures (corrupt, no text, blocked destination, parser wall/CPU/memory/result limit…) are never retried automatically; manual reprocessing stays available.
* **Safe to retry**: chunks are only visible after the atomic publish; a failed or retried attempt leaves the previous version intact. A failed *re*processing keeps serving the last published version.
* **Recovery**: `ingest.sweep` (Celery beat, every `INGEST_SWEEP_INTERVAL_SECONDS`, 2 min) re-publishes jobs whose broker message was lost (queued > 2 min), resets jobs whose worker died (heartbeat older than `INGEST_STUCK_AFTER_SECONDS`, re-checked at the update), fails jobs that already used all attempts (including pages an exhausted crawl left `processing`), and finishes pending storage deletions, including uploads that were never published (§9). It discovers work through two narrow `SECURITY DEFINER` functions (no BYPASSRLS role) and acts inside each organization's own context. It runs on its own `maintenance` queue and one-slot worker, so busy ingestion cannot delay it; beat also publishes it at start-up, and an untaken sweep expires after one interval.

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
| `PARSER_WALL_SECONDS`, `PARSER_CPU_SECONDS`, `PARSER_MEMORY_BYTES`, `PARSER_MAX_RESULT_BYTES` | 60, 30, 512 MiB, 32 MiB | Parser child budgets (§7) |
| `INGEST_SOFT_TIME_LIMIT_SECONDS`, `INGEST_HARD_TIME_LIMIT_SECONDS`, `CRAWL_MAX_TASK_SECONDS` | 120, 180, 3300 | Celery task limits (§8) |
| `INGEST_MAX_ACTIVE_PER_ORG`, `INGEST_DEFER_SECONDS`, `INGEST_SWEEP_INTERVAL_SECONDS` | 1, 2, 120 | Admission and recovery (§8) |
| `WORKER_MEMORY_LIMIT`, `WORKER_CPUS`, `WORKER_PIDS_LIMIT` (compose) | 2g, 2, 128 | Worker container limits (§8) |
| `RATE_LIMIT_UPLOAD_PER_MINUTE`, `RATE_LIMIT_SEARCH_PER_MINUTE` | 60 | Per organization / per user |

## 6. Known limitations

* Scanned documents are not OCR'd (they fail with `no_text`). Tables in PDFs are extracted as plain text; DOCX tables as `a | b` rows.
* Token counts are estimates; the default embedder is a lexical baseline — **use a real embedding model before relying on retrieval quality**.
* Crawling is same-host only, HTML only, no JavaScript rendering, no sitemap parsing; pages that disappear are reported (`not_seen`) but not auto-deleted.
* A document being reindexed after an *embedding model* change is not searchable until it is republished (old and new vectors are never mixed).
* Duplicate detection by normalized text hash catches identical text across formats, not near-duplicates.
* Postgres/`pgvector` HNSW with selective filters relies on iterative scans (`hnsw.iterative_scan`); very large tenants may need partitioning or per-tenant indexes later.
* Chatbot deletion is a soft delete: its chunks stay in the table (hidden from retrieval) until the purge job planned for the undo window.
* Parser isolation contains resources; it is not a security sandbox (§7).
* A Word file whose `document.xml` is larger than about 40 MiB now fails with `parse_resource_limit`, although the archive guard accepts up to 100 MiB (§7).


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

## 7. Parser isolation (AUD-05)

Every PDF, DOCX, TXT and HTML parse — uploads, reindexing, reprocessing, stored web pages and
live crawl pages — goes through `rag/parser_runner.py`, which starts a **fresh interpreter**
(`rag/parser_process.py`) per document. The parent keeps network fetching, storage, embedding and
database publication; the child only turns bytes into text blocks.

| Control | Enforced by | Default |
|---|---|---|
| Wall-clock deadline, from the moment the child reports its limits are set | parent kills the process group and reaps it (≤2 s) | 60 s |
| CPU seconds (`SIGXCPU`, then `SIGKILL`) | kernel, `RLIMIT_CPU` | 30 s |
| Address space | kernel, `RLIMIT_AS` | 512 MiB |
| No core dumps, no file writes, 32 descriptors, not dumpable | `RLIMIT_CORE/FSIZE/NOFILE`, `prctl` | fixed |
| Input size | parent, before spawning | upload / fetch limits |
| Result size; every field type-checked; JSON only, never pickle | parent | 32 MiB |
| Environment | empty (Windows keeps `SYSTEMROOT`, `WINDIR`); no inherited descriptors; no shell | — |
| Parent killed (hard time limit, OOM, `docker stop`) | `PR_SET_PDEATHSIG`; child-side `SIGALRM` backstop; `init: true` reaps | — |
| Document deleted or attempt superseded | parent polls the claim every second and kills the child | — |

Data moves over the two pipes only, so there are no temporary files to clean up. Child stderr is
discarded; logs carry `parser.finished` with pid, outcome, exit reason, duration, result size and
the limits in force — never document text.

**Platforms.** Containment is declared for **Linux** (production: the Docker image; Docker Desktop
on Windows/macOS). With `APP_ENV=staging|production`, a worker refuses to start, and a parser
refuses to run, where it is unavailable. Native Windows development (`--pool=solo`) still parses in
a child with the parent deadline, but has **no CPU/memory limits, no parent-death signal and no
Celery time limits**.

**Not covered.** The child runs as the worker's user with the same filesystem view and network
namespace: a parser exploit could read files that user can read (including `/proc/<pid>/environ` of
the worker), or open network connections. There is no seccomp profile, separate user or egress
policy. `robots.txt` is parsed in the worker (stdlib, 512 KiB cap).

**Measured fit** (QA host, one run each): the largest ordinary inputs the limits accept parsed
within 3.2 s wall, 3 s CPU and 333 MiB of address space. Word XML costs about 14× its size in
memory: 39 MiB of `document.xml` just fits, 44 MiB does not.
`docs/mvp-improvement/tools/measure_a5.py` repeats the measurement.

## 8. Worker limits, fairness and recovery (AUD-05)

**Time limits** (prefork pool only). Documents: soft 120 s, hard 180 s. Crawls: the worst case for
`CRAWL_MAX_PAGES_LIMIT` pages — `20 + pages × (10 s robots delay cap + 20 s fetch + 60 s parse +
30 s embedding)` with defaults — capped at `CRAWL_MAX_TASK_SECONDS` (3300 s hard, 3240 s soft; the
200-page default is therefore at the cap). Both stay under the broker's 3600 s visibility timeout.
A soft limit becomes a retryable `task_timeout`. A hard limit makes the pool send `SIGTERM` and,
100 ms later, `SIGKILL`: a `finally` block may or may not run, and a lost process runs none. Either
way the job stays `processing` until the sweeper resets it, at most one stuck
threshold plus one sweep interval later (about 17 minutes with defaults), and the last published
version keeps serving. The sweeper has its own worker, so that bound does not depend on a free
ingestion slot. The bound is for noticing: a job put back in the queue still waits for a slot to
run again.

**Health** (`python -m app.workers.health`, used by both compose files):

* `beat` is healthy only if the broker accepted a task within twice the sweep interval plus a
  minute. A running but stuck or disconnected scheduler turns unhealthy.
* `maintenance` is healthy only if the consumer answers through the broker, is consuming
  `maintenance`, and has no task older than 10 minutes. It does not depend on beat.

Docker reports an unhealthy container but does not restart it: monitoring must watch both. A
crashed `beat` or `maintenance` is restarted by the restart policy. Run exactly one `beat`.

**Fairness.** One organization runs at most `INGEST_MAX_ACTIVE_PER_ORG` (1) heavy jobs, documents
and crawls together, across all workers. The count comes from the job rows under a per-org advisory
lock, so no separate permit can leak. A job over the limit is not failed and uses no attempt: its
message is re-published after 2, 4, 8, then every 15 s (at most 40 times, after which the sweeper
takes over), and the organization's next waiting job is woken as soon as one finishes.
Consequence: a tenant's uploads wait behind that tenant's own running crawl.

**Container limits** (both compose files): 2 GiB memory with no additional swap, 2 CPUs, 128 PIDs,
`init: true`, sized for `--concurrency=2` (two 512 MiB parser children plus the Celery processes).
Raise all of them together with the concurrency. Compose values are only effective if the engine
applies them: verify with `docker inspect` or `/sys/fs/cgroup/{memory.max,memory.swap.max,cpu.max,pids.max}`.

## 9. Stored originals of web pages (A5.1)

Reprocessing and reindexing read a document's stored original, so who may change it matters as much
as who may publish chunks. An object write cannot be part of a database transaction, so a page's raw
HTML is **never written over an existing object**:

1. Before the upload, the new key (`orgs/{org}/chatbots/{bot}/documents/{doc}/g-{id}/original`) is
   recorded in `storage_deletions` as "delete this unless published", not before a time later than the
   writer can still be running (crawl hard time limit + 300 s). The check that this attempt still owns
   the job is made in that transaction.
2. The upload runs with no transaction open.
3. Publication (`documents.storage_key`, size and ETag) happens in the same fenced transaction as the
   chunks: it removes that record and queues the previous object for deletion. A document that has
   never published a version takes the new original at once, so it can be reprocessed.
4. A writer that finished but did not publish (superseded, deleted, failed) makes its object
   reclaimable immediately. A killed writer cannot; its object is reclaimed once its time has come.

The purge claims a record before touching its object, skips records that are not yet due, and never
deletes a key a document points at. A claimed key can no longer be published: the attempt fails with a
retryable `storage_error` instead of pointing at a deleted object. A document job refuses to publish
from an original that was replaced while it ran. Deleting a source or document locks it before reading
its keys, so a publication in progress cannot slip a new object past the deletion.

Consequences: a failed re-crawl of a published page keeps the previous original, size and chunks; an
interrupted upload can stay in storage for up to the grace period plus one sweep (about an hour with
defaults) and is not counted against the organization's storage limit; and cleanup needs `beat` and the
`maintenance` worker. Uploaded files are unaffected: each upload already has its own key. Documents stored
under the earlier `v0/original` keys keep working and move to a new key at their next publication.

