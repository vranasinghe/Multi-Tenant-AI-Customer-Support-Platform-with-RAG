# Developer Setup Guide

| Field | Value |
|---|---|
| Status | Current as of Phase 0 (foundations) — 2026-11-21 |
| Applies to | Windows 11, macOS, Linux |
| Related | [ARCHITECTURE](ARCHITECTURE.md) · [ROADMAP](ROADMAP.md) · [DECISIONS](DECISIONS.md) |

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker Desktop (or Docker Engine + Compose v2) | Engine 25+, Compose 2.24+ | Required for Postgres, Redis and the full stack |
| Node.js | 24 LTS (see `.node-version`) | |
| pnpm | 11.28.x (pinned in `package.json` → `packageManager`) | `corepack enable` once (admin shell on Windows), or `npm i -g pnpm@11.28.12` |
| uv | ≥ 0.13 | `uv self update` if older. uv installs the pinned Python 3.13 itself |
| Git | any recent | Line endings are normalized by `.gitattributes` |

Python does **not** need to be installed separately. `uv` downloads the interpreter pinned in `services/api/.python-version`.

## 2. First run (whole stack in Docker)

```powershell
Copy-Item .env.example .env
```

```powershell
pnpm install
```

```powershell
docker compose up -d --build --wait
```

```powershell
pnpm smoke
```

Then open:

| URL | What |
|---|---|
| http://localhost:3000 | Web status page (shows API, database, migration and Redis status) |
| http://localhost:8000/docs | API OpenAPI UI (disabled when `APP_ENV=production`) |
| http://localhost:8000/healthz | API liveness |
| http://localhost:8000/readyz | API readiness: Postgres + pgvector, migrations at head, Redis |
| http://localhost:3000/api/health · `/api/ready` | Web liveness · web→API readiness |

`pnpm smoke` checks every hop: browser→web, web→API (over the container network), API→Postgres/pgvector/migrations/Redis, and API→Celery worker→Redis (broker + result backend), including request-ID propagation. Every line should show ✓.

### What `docker compose up` starts

| Service | Image / build | Purpose |
|---|---|---|
| `postgres` | `pgvector/pgvector:0.8.7-pg18-bookworm` | Database. On first start, `infrastructure/postgres/init` creates the unprivileged `platform_app` role |
| `redis` | `redis:8.10.3-alpine` | Celery broker/result backend, rate-limit counters (ephemeral in dev) |
| `mailpit` | `axllent/mailpit:v1.34.0` | Local SMTP sink: every verification, reset and invitation email lands in the UI at http://localhost:8025 |
| `migrate` | `services/api` (dev target) | Runs `alembic upgrade head` as the schema owner, then exits |
| `api` | `services/api` (dev target) | FastAPI with hot reload (source bind-mounted) |
| `storage` | `rustfs/rustfs:1.0.6` | S3-compatible private object storage for uploaded originals (MinIO no longer publishes images; production uses real S3) |
| `storage-init` | `services/api` (dev target) | Creates the private bucket (`python -m app.cli init-storage`), then exits |
| `worker` | `services/api` (dev target) | Celery worker on all queues (document processing runs on `ingest`, crawls on `crawl`) |
| `beat` | `services/api` (dev target) | Celery beat: `ingest.sweep` every 2 minutes (stuck jobs, lost messages, storage cleanup) |
| `web` | `apps/web/Dockerfile` | Production build of the Next.js app |

Host ports bind to `127.0.0.1` only. Postgres is published on **55432** so it never collides with a natively installed PostgreSQL on 5432. Change any port in `.env` (`*_HOST_PORT`).

## 3. Day-to-day workflows

### Backend changes
The `api` container hot-reloads on file changes (`WATCHFILES_FORCE_POLLING=true` makes this work on Windows/macOS bind mounts). Restart the worker after task changes:

```powershell
docker compose restart worker
```

### Frontend changes (hot reload)
The `web` container runs a production build. For hot reload, run Next.js natively against the Dockerized API:

```powershell
docker compose stop web
```

```powershell
pnpm dev:web
```

`apps/web/next.config.ts` loads the repo-root `.env`, so native runs share one configuration with the API.

### Running the API/worker natively (optional)
```powershell
docker compose stop api worker
```

```powershell
pnpm api:dev
```

```powershell
pnpm worker:dev
```

- `api:dev` uses `uvicorn --reload`. On Windows that also selects the Selector event loop that async psycopg requires.
- `worker:dev` uses `--pool=solo` because Celery's prefork pool does not support Windows.

### Database migrations
```powershell
pnpm db:migrate
```

Create a new migration (after adding models in `services/api/app/models`):

```powershell
uv run --directory services/api alembic revision --autogenerate -m "describe change"
```

Migrations run as the schema owner (`MIGRATION_DATABASE_URL`). The app runs as `platform_app`, which has DML rights only, no superuser and no `BYPASSRLS` (docs/DATABASE.md §4.1).

### Reset local data
```powershell
docker compose down -v
```

This deletes the Postgres volume. The next `up` re-runs the role bootstrap and migrations.

## 4. Quality checks

Run everything CI runs, except the Docker job:

```powershell
pnpm check
```

| Command | What it does |
|---|---|
| `pnpm format` / `pnpm format:check` | Prettier for TS/JS/JSON/CSS/YAML (Markdown is excluded on purpose) |
| `pnpm lint` | ESLint: `eslint-config-next` for the web app, typescript-eslint elsewhere |
| `pnpm typecheck` | `tsc --noEmit` in every package |
| `pnpm test` | Vitest (web + widget) |
| `pnpm build` | Next.js production build + widget bundle with a 10 KB gzip budget check |
| `pnpm api:lint` / `pnpm api:format` | Ruff lint + format check / auto-fix |
| `pnpm api:typecheck` | mypy (strict) |
| `pnpm api:test` | Pytest unit tests (no services needed) |
| `pnpm api:test:integration` | Pytest integration tests (needs the Docker stack running) |
| `pnpm smoke` | End-to-end checks against the running stack |
| `pnpm --filter @acs/web test:e2e` | Playwright against the real stack (needs Docker incl. `worker`): chatbot wizard, and upload → index → search → delete. Uses installed Chrome (`E2E_BROWSER_CHANNEL`) |

Integration tests create their own throwaway database (from `MIGRATION_DATABASE_URL`, which needs the schema-owner role), run the real migrations into it and drop it afterwards; they also use Redis DB 15 and flush it. They never touch your development data. The tenant-isolation suite lives in `tests/integration/tenancy/` (database level) and `tests/integration/api/test_tenant_isolation.py` (HTTP level); both must pass before merging.

`python -m app.cli check-rls` fails if any table with an `org_id` column lacks forced Row-Level Security and a policy (CI runs it after migrations).

If `pnpm` is not on your PATH (Windows without admin `corepack enable`), prefix commands with `corepack`, e.g. `corepack pnpm -r --if-present test`.

Ingestion has three more layers (see [INGESTION.md](INGESTION.md), [RAG_EVALUATION.md](RAG_EVALUATION.md)): unit tests in `tests/unit/rag/` (extraction, chunking, SSRF fetcher, crawler), integration tests in `tests/integration/api/test_knowledge_*.py` (HTTP API with workers run in-process against a memory object store), and the evaluation harness in `tests/integration/api/rag_eval/` (deterministic, with a committed baseline). A full-stack smoke test (real API, Celery worker, S3 storage, Postgres) is opt-in:

```powershell
docker compose exec -e LIVE_INGESTION=1 api pytest tests/integration/test_live_ingestion.py
```

Integration tests can also run inside the API container:

```powershell
docker compose exec api pytest -m integration
```

## 5. Configuration and environment variables

- **Template:** `.env.example` (committed, placeholders only). **Your copy:** `.env` (git-ignored, never commit).
- **API:** `services/api/app/core/config.py` (pydantic-settings) validates every value at startup. Wrong driver schemes, malformed CORS origins and missing URLs fail fast with a clear message. With `APP_ENV=production` the API also refuses placeholder (`change-me`) credentials, non-JSON logs and non-HTTPS CORS origins.
- **Web:** `apps/web/src/env.ts` (zod) validates server variables when the server starts (`instrumentation.ts`) and `NEXT_PUBLIC_*` variables when the config loads, because those are inlined at build time.
- Host-side URLs use `127.0.0.1` rather than `localhost`. On Windows, `localhost` resolves to `::1` first while Docker publishes on IPv4 only, which stalls Postgres/Redis clients for minutes. Browser-facing URLs stay `localhost`.

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_*` | compose | Local DB name, owner and runtime role credentials |
| `*_HOST_PORT` | compose | Host port mapping |
| `APP_ENV` | api, worker | `local` · `test` · `staging` · `production` |
| `LOG_LEVEL`, `LOG_FORMAT` | api, worker, web | Level (case-insensitive) · `console` or `json` |
| `DATABASE_URL` | api, worker | Runtime role, `postgresql+psycopg://` scheme required |
| `MIGRATION_DATABASE_URL` | alembic | Schema-owner role |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | api, worker | Redis DBs 0/1/2 |
| `CORS_ALLOWED_ORIGINS` | api | Comma-separated browser origins allowed to call the API with credentials (also the CSRF `Origin` allowlist) |
| `WEB_BASE_URL` | api | Base URL of the web app, used for links in emails (HTTPS required in production) |
| `EMAIL_BACKEND`, `SMTP_*`, `EMAIL_FROM` | api | `smtp` (Mailpit locally) or `log`; `log` prints token links and is refused in production |
| `API_INTERNAL_URL` | web (server) | How the Next.js server reaches the API |
| `NEXT_PUBLIC_API_URL` | web (browser) | How browsers reach the API (build-time) |

## 6. Observability in development

- **Request IDs.** Every request gets an `X-Request-ID`. A valid client-supplied value (8–128 chars of `[A-Za-z0-9._-]`) is kept, anything else is replaced. The web proxy (`apps/web/src/proxy.ts`) assigns it, the web→API readiness call forwards it, the API middleware binds it to every log line, and Celery tasks inherit it through message headers.
- **Logs.** The API and worker use structlog (`LOG_FORMAT=console` locally, `json` in deployed environments). The web app writes one JSON object per line. Successful `/healthz`/`/readyz` probes log at DEBUG so they don't flood the output.

```powershell
docker compose logs -f api worker
```

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `ports are not available … 5432/6379/8000/3000` | Something else uses the port. Set the matching `*_HOST_PORT` in `.env` |
| `/readyz` shows `migrations: database has not been migrated` | Run `pnpm db:migrate` |
| Postgres role/password changes have no effect | Init scripts only run on an empty volume. Run `docker compose down -v` |
| `uv: required version >=0.13` | `uv self update` |
| `pnpm: command not found` | `corepack enable` (admin shell) or `npm i -g pnpm@11.28.12` |
| Native pytest on Windows hangs connecting to the DB | Use `127.0.0.1`, not `localhost`, in `.env` URLs (see §5) |
| `EnvValidationError` / pydantic `ValidationError` at startup | The message names the bad variable. Compare with `.env.example` |

## 8. Dependency notes

- **Versions are pinned exactly** (`package.json`, `pyproject.toml`) and locked (`pnpm-lock.yaml`, `uv.lock`). Docker base images are pinned to patch versions, GitHub Actions to commit SHAs. Dependabot proposes weekly grouped updates.
- **TypeScript 6.0.** typescript-eslint 8.x supports TypeScript < 6.1, so TS 7 waits until it does.
- **ESLint 10.** ESLint 9 is end-of-life. `eslint-plugin-import`, `eslint-plugin-jsx-a11y` and `eslint-plugin-react` (via `eslint-config-next`) haven't widened their peer ranges to 10 yet, so `pnpm-workspace.yaml` allows that explicitly. Their rules were verified to fire under ESLint 10 (react-hooks, next, jsx-a11y probes). Remove the override once upstream releases support.
- **shadcn/ui.** Components live in `packages/ui` (monorepo layout, `components.json` in both `apps/web` and `packages/ui`). Add components from the repo root:

```powershell
npx shadcn@latest add dialog --cwd apps/web
```

  Then check generated imports: CLI 4.23 rewrote the `cn` import to a non-existent `cn` package and added stray deps to `apps/web`. Imports should be `../lib/utils`, and new runtime deps belong in `packages/ui/package.json`. `pnpm dlx shadcn` currently fails on a broken transitive dependency, so use `npx`.
- **httpx2.** Starlette's test client now prefers `httpx2` (the maintained successor of `httpx`), so it's the test dependency.


## 9. AI provider transport policy (AUD-03)

Both configured OpenAI-compatible providers require an ASCII HTTPS base URL with a valid hostname
and port. Ordinary base paths such as `/v1` or `/deployment/v1` are supported. Embedded userinfo,
query strings (including empty `?`), fragments, percent encoding, whitespace/control characters,
backslashes, dot segments, doubled path separators, malformed/ambiguous authorities and
noncanonical numeric hosts/ports are rejected. Use ASCII IDNA/punycode hostnames when needed.
Paths accept letters, digits, `/`, `_`, `.`, `~` and `-`; trailing slashes are normalized.

The policy applies at Settings validation and API/worker startup, including explicitly supplied
settings. `APP_ENV=staging|production` always requires HTTPS and rejects the local exception flag,
even when no network provider is selected. No setting disables TLS verification. Provider URLs
are operator configuration, never chatbot/tenant input; HTTPS private services are permitted.
This is separate from the website crawler's public-IP SSRF policy.

`ALLOW_INSECURE_LOCAL_PROVIDERS=false` is the default and is wired consistently to API, workers
and beat through Compose's shared environment. A local/test operator may explicitly set it true
for a disposable HTTP provider bound to `localhost`, canonical IPv4 loopback (127/8), or `[::1]`.
Mapped IPv6, host.docker.internal, Compose service names, LAN addresses, 0.0.0.0 and public hosts
are refused for HTTP. Localhost is an explicit local name exception; it is not a DNS-pinning or
host-compromise defense. Remember that container loopback refers to that container, not the host.
Prefer TLS; do not broaden the exception to make a container route work. Use a verified HTTPS
endpoint/reverse proxy for a container or LAN service. Enabling this option is a deliberate new
local chat-provider capability; previously the chat settings permitted HTTPS only.

Upgrade checklist:

1. Keep provider keys server-side and outside URLs. Use only placeholders in shared configuration.
2. Replace HTTP production/staging endpoints with the provider's final HTTPS base URL. Fix the
   provider's certificate chain/hostname; never disable certificate verification.
3. Configure the final endpoint directly: no 301/302/303/307/308 redirect is followed, including
   same-host and HTTPS-to-HTTP redirects. Providers needing query-based API versions, non-Bearer
   auth or encoded paths require a separately reviewed adapter; do not bypass the URL policy.
4. Provider clients ignore HTTP_PROXY, HTTPS_PROXY, ALL_PROXY, NO_PROXY (and lowercase variants),
   SSL_CERT_FILE and SSL_CERT_DIR. The isolated query child also does not inherit those variables.
   The default HTTP client's installed CA bundle is used. Environments requiring a custom CA or
   authenticated proxy need explicit reviewed configuration in a later task; no ambient override
   or verification bypass is supplied here. OS/network-level routing is outside this guarantee.
5. Restart API, worker and beat together after an operator configuration change. This task does
   not set a live/paid provider, change the embedding model/dimensions or require reindexing.

Settings exception strings suppress raw input and transport errors use fixed messages/codes.
Do not log Settings objects, raw `ValidationError.errors()`/JSON, provider payloads or low-level
HTTP request diagnostics; structured error methods may still contain input unless callers use
`include_input=False` (and omit exception context). Suppression of exception display is not a
secrets-history scanner or permission to log configuration dumps.

Deterministic local verification (synthetic TLS certificates, no paid requests):

```powershell
docker compose exec -T api pytest tests/unit/mvp_improvement/test_provider_transport.py tests/unit/audit/test_prompt_evidence.py -q
```

The test CA is injected only into test transports. Untrusted, expired and hostname-mismatched
chains fail before request credentials/text are sent; the system trust store is unchanged.
The public test leaf key under tests/support/provider_tls is never a runtime credential.
