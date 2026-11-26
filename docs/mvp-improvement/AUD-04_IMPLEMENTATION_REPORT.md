# AUD-04 — Trusted proxy security

Date: 26 November 2026 (Asia/Colombo). Scope: Milestone A4 / AUD-04, Section 9 of the approved implementation plan.

## Executive summary and decision

**AUD-04: PASS for local validation of the proxy-trust scope.** The runtime image no longer trusts forwarding headers from every peer. No peer is trusted unless an operator lists it, and unsafe values stop startup. Verified over real HTTP against the production-target image: **17 of 17 runtime checks pass** (the unchanged image failed them), plus **197 new unit cases**.

**The validation run was not fully green.** The final full backend run was **1,005 passed / 2 failed / 17 skipped**. Both failures also occurred in a full run made **before any A4 change** (808 passed / 2 failed):

1. `test_strict_capacity[100]` (AUD-01, observation PERF-01): success P95 above the 2,000 ms gate in every run today. AUD-01 therefore stands at **17 of 18**.
2. `test_chat_migration_roundtrip`: the `0007 → 0004` downgrade fails in a full run.

Backend Ruff lint also fails on **five pre-existing errors** in `migrations/versions/20261125_0007_conversation_analytics.py`. None of these three items was fixed here.

**Production ingress verification: BLOCKED** (no authorized deployment environment). **Overall MVP readiness: NOT READY.**

## Preflight

`.git` is present (the A1–A3 note that it was absent no longer applies). HEAD `db4d352` on `cursor/phase-7-conversation-analytics-327e`. Four tracked files already had uncommitted changes (`.prettierignore`, `answer-text.tsx`, `docker-compose.prod.yml`, `globals.css`) and `docs/ui-ux/` was untracked; they are preserved. Before editing, a SHA-256 inventory of 699 files and a patch of the uncommitted changes were recorded: [preflight](evidence/AUD-04/preflight.json), [hashes](evidence/AUD-04/before_hashes.json), [patch](evidence/AUD-04/pre_existing_uncommitted.patch). No commit, branch, push or history change was made.

Phase 7 was added after the A3 result of 795 tests, so a new pre-change baseline was taken: [log](evidence/AUD-04/baseline-backend-full.log), [JUnit](evidence/AUD-04/baseline-backend-full.xml).

**Test environment.** The developer's `.env` configures a real AI provider with keys. To avoid paid calls, all backend, smoke and browser validation ran on a disposable Compose project (`acs-a4-qa`) with its own volumes, synthetic credentials, the `demo` LLM and `hash` embeddings. It was removed afterwards. For the standard-port phase the developer's containers were stopped and then restarted; their volumes were not touched. Compose could not restart them through `docker compose start` because the existing stale `migrate` container fails; `api` and `worker` were started directly and `/readyz` returned ok.

## Original defect and root cause

The runtime `CMD` passed `--proxy-headers --forwarded-allow-ips "*"`. Uvicorn then rewrote `request.client` and the scheme from headers sent by any peer. `RequestMeta` correctly reads `request.client`, so IP rate limits and the audit IP prefix used whatever the caller wrote.

A second route to the same state was found while reading Uvicorn 0.54.0: its CLI also reads `UVICORN_FORWARDED_ALLOW_IPS` and `UVICORN_PROXY_HEADERS`, and with nothing configured it trusts `127.0.0.1,::1`.

## Baseline evidence

Reproduced with the unchanged runtime image on a disposable Docker network with synthetic documentation addresses ([log](evidence/AUD-04/baseline-runtime-http.log), [scheme log](evidence/AUD-04/baseline-runtime-scheme-host-fixed.log)):

| Observation (demonstrated locally) | Baseline result |
|---|---|
| 25 logins from one direct peer, a different forged `X-Forwarded-For` each | **no 429 at all** (limit is 10/minute) |
| Forged `X-Forwarded-Proto: https` over plain HTTP | redirect came back as `https://` |
| Chain with a client-written prefix through a proxy | limiter counted the **client-written** address |
| `FORWARDED_ALLOW_IPS=*`, `/0` or junk | server started or failed for unrelated reasons |

- **Source-confirmed:** the wildcard in the image command.
- **Demonstrated locally:** the four rows above.
- **Not verified:** whether any real deployment exposes the API directly. Behind a proxy that overwrites the header, the old setting might not have been exploitable.

The first scheme run (`baseline-runtime-scheme.log`) used a client that sent two `Host` headers; the test client was fixed and rerun. Both logs are kept.

## Implementation

- `app/core/proxy_trust.py` (new): strict validation of `FORWARDED_ALLOW_IPS`.
- `app/core/config.py`: the `forwarded_allow_ips` setting (default empty); `UVICORN_FORWARDED_ALLOW_IPS` and `UVICORN_PROXY_HEADERS` are refused.
- `app/server.py` (new): the launcher. It passes the validated list to `uvicorn.run` explicitly and does not install the proxy middleware when the list is empty. It accepts only `--host`, `--port`, `--reload`.
- `Dockerfile`: both stages start through the launcher; `FORWARDED_ALLOW_IPS=""` is declared; the wildcard is gone.
- `docker-compose.yml`, `docker-compose.prod.yml`: pass `FORWARDED_ALLOW_IPS` to the `api` service only, empty by default.
- `package.json` (`api:dev`), `app/main.py` (docstring), `.env.example`, `.env.production.example`.
- `deploy/deploy.sh`: includes an operator-created `docker-compose.ingress.yml` and warns when the trust list is empty.
- Documentation: `DEVELOPMENT.md` section 10, `DEPLOY_CONTABO.md` "Trusted ingress", `WIDGET_DEPLOYMENT.md`, additive note in `PHASE2_SECURITY_REVIEW.md`.

Header parsing remains Uvicorn's. `request_meta.py` is unchanged. No dependency, migration, provider-transport, CSRF, CORS, cookie, widget or rate-limit change.

**Accepted values:** comma-separated literal IPv4/IPv6 addresses or CIDR networks. **Refused in every environment** (stricter than "deployed only"): `*`, `/0`, networks broader than IPv4 `/8` or IPv6 `/16`, unspecified addresses, host names, ports, brackets, zone IDs, netmask notation, IPv4-mapped IPv6, host bits set and empty entries.

**Precedence:** an explicit constructor value, then the environment variable, then `.env` files for native runs, then empty. The launcher passes the result explicitly, so Uvicorn's environment defaults are not consulted.

**Behavior changes to note:** `uvicorn` command-line `UVICORN_*` environment settings no longer apply to the API process, since it is started with `uvicorn.run`. Native `pnpm api:dev` no longer trusts loopback proxy headers.

## New regression tests

- `tests/unit/mvp_improvement/test_proxy_trust.py` — **197 cases**: defaults, valid IPv4/IPv6/CIDR, rejected and malformed values, untrusted peers, single and multi-hop chains, untrusted address inside a chain, duplicate/empty/junk chains, forged schemes, one limiter identity under forged variations, launcher-to-middleware consistency, launcher argument rejection, Dockerfile commands.
- `tests/integration/test_runtime_proxy_trust.py` — **17 cases** run from the host against a built runtime image. It is skipped (the 17 skips above) unless `RUNTIME_PROXY_IMAGE` is set, so **CI does not run it today**.

Test-first record: the unit file first failed on the missing module ([unit-red](evidence/AUD-04/unit-red.log)); the behavioral failures are the runtime baseline. After implementation: [197 passed](evidence/AUD-04/unit-green-first.log). The file then had lint and type fixes only, and passed again in the full run.

**Last change after the full run:** the diff review found that the `ENV` block in the Dockerfile had lost a line continuation, leaving two assignments on one line (same effective values). It was reformatted; the runtime image was rebuilt, all 17 runtime cases passed again ([final runtime log](evidence/AUD-04/final-runtime-http.log)), and the proxy unit tests with both original audit regressions passed (199, [log](evidence/AUD-04/final-unit.log)). The full backend suite was not repeated for this formatting change. The developer's `.env` secrets were not found in any A4 file; the only match was the published `change-me` placeholders.

## Trusted and untrusted peer behavior (runtime image)

[Final log](evidence/AUD-04/runtime-http.log), [JUnit](evidence/AUD-04/runtime-http.xml): 17 passed in 55.65 s.

| Scenario | Result |
|---|---|
| Direct peer, trust unset / empty / only another proxy; 25 forged addresses | at least 5 × 429; limiter counted only the real peer |
| Direct peer forging `https` | ignored |
| Trusted proxy, single hop | limiter counted the forwarded client |
| Client-written prefix + real client + two trusted hops (one IPv6) | real client |
| Duplicate headers | one chain; IPv6 client resolved |
| Empty chain from the proxy | proxy address kept |
| `https` from the proxy; `javascript`, `https, http`, `HTTPS` | applied; ignored |
| `*`, `0.0.0.0/0`, `::/0`, junk, in staging and production | startup fails naming the setting |
| `UVICORN_FORWARDED_ALLOW_IPS=*`, `UVICORN_PROXY_HEADERS=true` | startup fails |
| Image configuration | no `*` in `CMD`; `FORWARDED_ALLOW_IPS` declared empty |

Rate-limit identity was read from the hashed Redis keys, not inferred from status codes alone.

**Documented limitation:** Uvicorn does not check that a chain entry is an IP address. If a *trusted* proxy forwards junk as the rightmost entry, that string becomes the client identity (no IP prefix is recorded). The ingress contract therefore requires the proxy to append or replace the header. Junk to the left of an appended address is ignored.

**IPv6:** trusted IPv6 peers were verified at middleware level only. The runtime image binds `0.0.0.0`, so an IPv6 peer cannot connect to it; this binding was not changed.

## AUD-01 / AUD-02 / AUD-03 and existing controls

| Group | Pre-change full | Final full | Targeted preservation |
|---|---|---|---|
| AUD-01 (18) | 1 fail | **1 fail** | **1 fail** |
| AUD-02 (32) | pass | pass | pass |
| AUD-03 (159) | pass | pass | pass |
| Original audit regressions (2) | pass | pass | pass |
| AUD-04 (197) | — | pass | pass |
| Auth, route permissions, tenant isolation (65) | pass | pass | pass |
| Widget integration (12) | pass | pass | pass |

[Preservation run](evidence/AUD-04/preservation.log): 741 passed / 1 failed. It also included rate-control, origin, security-primitive, policy, RAG, provider and worker unit tests.

## Full backend results

| Run | Passed | Failed | Skipped | pytest time |
|---|---|---|---|---|
| Pre-change baseline | 808 | 2 | 0 | 164.47 s |
| Final | 1,005 | 2 | 17 | 158.83 s |

The difference in passes is exactly the 197 new unit cases. Both runs used `LIVE_INGESTION=1`; in the final run the live API under test was started by the new launcher. Reruns are not counted as extra coverage.

## Static, build, RLS, smoke and browser

| Check | Exit | Result |
|---|---|---|
| `ruff check .` | **1** | 5 pre-existing errors in migration `0007`, unchanged from HEAD |
| `ruff check . --extend-exclude <that file>` | 0 | all checks passed |
| `ruff format --check .` | 0 | 188 files formatted |
| `mypy` (strict) | 0 | no issues, 186 files |
| `docker build --target runtime` (`acs-api:mvp-a4-local`) | 0 | built |
| `python -m app.cli check-rls` | 0 | no unprotected tables |
| `node scripts/smoke.mjs` | 0 | all checks passed, including the worker round trip |
| Playwright, unmodified | 0 | **6 passed** (19.8 s) |
| Compose rendering, `bash -n`, Prettier | 0 | passed |

Evidence IDs: `static-final` (format, mypy), `static-lint-default`, `static-lint-excluding-preexisting`, `runtime-build`, `rls`, `smoke`, `browser-run`, `compose-config`, `format-and-syntax`. Each has a `.json` (command, exit code, duration) and `.log` in [evidence/AUD-04](evidence/AUD-04/).

Failed attempts kept: `static-first` (lint and type errors in the new test file, then fixed; its lint step also listed the five old errors); `static-final` exited 1 because its second lint step used `--exclude`, which replaced Ruff's default exclusions and scanned the host `.venv`; `browser` ran no tests because the capture tool's path setting broke the `corepack` shim.

**Browser routing (A3 observation):** checked first. The web server answered 200 on both IPv4 and IPv6, so **no routing workaround** was used. The API publishes IPv4 only; the browser reached it without changes.

The web app was served by the host's Next.js development server, not a production web build.

## PERF-01 — open performance observation

A1 success P95 at concurrency 100, gate 2,000 ms:

| Run | P95 (ms) | Success / rejected / unexpected | Gate |
|---|---|---|---|
| A3 full runs (22 Nov) | 2,004.02; 2,011.51; 1,925.10 | — | fail; fail; pass |
| A4 pre-change baseline | **2,124.37** | 42 / 58 / 0 | **fail** |
| A4 final full | **2,084.73** | 41 / 59 / 0 | **fail** |
| A4 preservation | **2,117.42** | 42 / 58 / 0 | **fail** |

These are all the capacity runs made in A4. No pool, admission, threshold or assertion was changed, and no run was repeated to obtain a pass. All requests were handled; only latency missed the gate.

Facts bearing on interpretation: the failure predates the A4 changes; the developer's own stack was running on the same machine during all three A4 runs; and the code now includes Phase 7. **No cause has been established.** It does not block the AUD-04 scope, which does not touch the chat path, but it does block calling AUD-01 or Milestone A complete. Recommendation: separate performance remediation, starting with a controlled measurement on an idle host.

## Pre-existing migration failure (not in scope)

`test_chat_migration_roundtrip` passes when run alone ([detail](evidence/AUD-04/baseline-migration-detail.log)) and fails in a full run, before and after A4. A likely explanation is that `0007`'s downgrade re-adds a foreign key on `chat_usage` that rows left by earlier tests violate. **This was not verified.** It matters for rollback of Phase 7, not of AUD-04.

## Production ingress contract and deployment limitations

Required: public requests enter only through a trusted proxy; the proxy replaces untrusted forwarding headers; only that proxy can reach the API; PostgreSQL, Redis and storage stay private; the exact proxy address is configured; HTTPS terminates at the proxy.

**Action needed before deploying this change:** `docker-compose.prod.yml` puts Caddy in front of the API. With `FORWARDED_ALLOW_IPS` empty, **all visitors share Caddy's address**: the login and sign-up IP limits become global and audit rows hold Caddy's network. `DEPLOY_CONTABO.md` "Trusted ingress" gives the fixed-address setup. No subnet or address is defaulted. Its Compose rendering was checked; **Caddy itself was not run** (no image available locally) and its header replacement is taken from its documented default.

The application does not derive cookie security from the request scheme (`__Host-` cookies are always `Secure`). With no trusted proxy, framework redirects such as trailing-slash redirects are built with `http://` behind a TLS-terminating proxy.

**BLOCKED:** direct-ingress denial, proxy header sanitation, real proxy addresses, TLS termination and production exploitability.

The developer's running containers still use their previously built image. They load the new source, but start `uvicorn` directly until rebuilt (`docker compose up -d --build`).

## Rollback considerations

No data or schema change; rollback is code and configuration only. **Never restore `--forwarded-allow-ips "*"`.** If proxy trust misbehaves, set `FORWARDED_ALLOW_IPS` empty (direct-peer identity) or correct the explicit list. An invalid value stops startup, so validate a changed value before restarting production. No rollback was performed.

## Stop boundary

AUD-05, AUD-06, AUD-07 and Milestones B–J were not started. No paid provider was configured or called, nothing was deployed or pushed, no threshold was lowered, and original audit files and A1–A3 evidence are unchanged (see [artifact validation](evidence/AUD-04/artifact-validation.json)).
