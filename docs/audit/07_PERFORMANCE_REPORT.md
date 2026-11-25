# Performance validation

Acceptance: **FAIL**. A HIGH database-pool starvation defect prevents safe chat admission under modest concurrency. Raw samples, statuses and process resource values are in `evidence/performance.json`; a fresh ten-request confirmation is in `performance_confirmation.json` and `pool_regression.log`.

## Environment and method

Local Docker stack, 32 logical CPUs reported to the container; PostgreSQL/pgvector and Redis are real. The harness invokes actual FastAPI routes through ASGI against a disposable database, using a deterministic LLM fixture with 10 ms delay, one text delta, and usage 100 input/10 output tokens. No paid API or high-volume real-model load was used. No reverse proxy, browser or provider network is included.

The default org generation concurrency cap of three is retained. Request/minute and monthly usage limits are raised only in the audit test so quota depletion cannot mask infrastructure bottlenecks. Database pool defaults remain five plus five overflow. Each stage issues max(10, concurrency) requests through a bounded semaphore; therefore 170 requests are measured across four stages. This is a short saturation probe, not a sustained production capacity benchmark. A 40-second stage deadline bounds hangs.

Duration is full request completion latency including failed responses, not pure generation time. TTFT is an ASGI send callback's first SSE delta, not browser-observed network TTFT. Percentiles use ordered index floor((N-1)*p), including the reported P50; small-sample values should not be overinterpreted. Successful rate is HTTP-200 completions divided by stage wall time; error rate includes HTTP >=400 or harness timeout. Status 200 alone would not prove a correct answer.

| Concurrency | Requests | HTTP statuses | P50 ms | P95 ms | Successful TTFT P95 ms | Successful req/s | HTTP error rate | CPU s | Peak RSS KiB |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 10 | {'200': 10} | 31.08 | 32.80 | 26.96 | 29.27 | 0% | 0.1783 | 144120 |
| 10 | 10 | {'500': 10} | 30191.39 | 30279.74 | None | 0.00 | 100% | 0.1164 | 147192 |
| 50 | 50 | {'500': 50} | 30764.77 | 31331.23 | None | 0.00 | 100% | 0.5525 | 153336 |
| 100 | 100 | {'500': 100} | 31004.74 | 31906.54 | None | 0.00 | 100% | 0.8067 | 161528 |

CPU is process RUSAGE_SELF elapsed CPU seconds per stage; it excludes database, worker and host CPU. RSS is the process lifetime peak, not a new per-stage allocation measurement. No container CPU utilization percentage is inferred from these values. Null TTFT means there were no successful streamed replies in that stage.

## Confirmation and root cause

The original 10/50/100 stages produced 160 HTTP 500 responses around the 30-second database-pool wait. A fresh ten-concurrent-request test produced **one HTTP 200 and nine HTTP 500s**, with P50 30,148.55 ms and P95 30,236.69 ms. The one success emitted its first delta only after about 30,287.92 ms. This schedule-dependent variation supports resource starvation rather than a deterministic provider rejection.

Tracebacks show `sqlalchemy.exc.TimeoutError`, QueuePool size 5 overflow 5, timeout 30 seconds. Authentication's request-scoped session retains a connection while chat preparation tries a second session in `find_conversation`, before admission control can reject excess requests. See AUD-01 for precise source locations, impact, proposed fix and regression criteria. Increasing the pool alone does not resolve the resource-ordering problem.

## Retrieval, document processing and unmeasured dimensions

One hundred sequential hash/hybrid retrieval API calls measured median 9.98 ms/P95 13.38 ms. Twenty tiny text document upload/controlled-processing operations measured median **38.65 ms**; raw values are in `business_workflow.json`. The latter uses the fixture object store and deterministic job drain and excludes distributed worker scheduling, S3 network and real embedding latency. PDF/DOCX persistence was verified separately without a general throughput claim.

Real model TTFT/generation latency, large-document throughput, sustained multi-tenant load, production proxy/network overhead, query EXPLAIN plans, per-query database timings, full worker/container resource metrics and long-term memory growth are **NOT_TESTED**. Successful HTTP-200 total response latency at concurrency one is the only full-chat local latency baseline here. After fixing pool ordering, repeat all stages and add a second-tenant read/health probe; overload must return controlled admission responses rather than HTTP 500s.
