# AI Customer Support Chatbot SaaS

Phase 6 now includes a versioned, embeddable streaming widget, verified-origin controls, anonymous resumption and live dashboard installation preview. See [WIDGET_DEPLOYMENT.md](docs/WIDGET_DEPLOYMENT.md) for installation and rollout.

Multi-tenant platform for businesses to build RAG-powered support chatbots on their own knowledge, embed them on websites, and connect Telegram/WhatsApp.

> **Status:** Foundations, authentication/tenancy, chatbot management, ingestion/retrieval and the Phase 5 conversation engine are implemented. Chat includes a dashboard playground and restricted public-session APIs. Configure a real provider before using AI generation; the offline demo is a transport fixture. See [docs/CHAT_ENGINE.md](docs/CHAT_ENGINE.md) and [docs/ROADMAP.md](docs/ROADMAP.md).

## Quick start

Prerequisites: Docker Desktop, Node.js 24, pnpm 11 (`corepack enable`), uv ≥ 0.13. Full guide: **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)**.

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

Then open http://localhost:3000 (status page) and http://localhost:8000/docs (API).

## Repository layout

```
├── apps/
│   ├── web/                 # Next.js 16 dashboard (App Router, Tailwind 4, shadcn/ui)
│   └── widget/              # Embeddable chat widget loader (Vite, IIFE bundle)
├── services/
│   └── api/                 # FastAPI + Celery (Python 3.13, SQLAlchemy 2.1, Alembic)
│       ├── app/             # api/ core/ models/ schemas/ services/ rag/ integrations/ workers/
│       ├── migrations/
│       └── tests/           # unit/ (no services) · integration/ (Postgres + Redis)
├── packages/
│   ├── ui/                  # Shared shadcn/ui components + Tailwind theme
│   └── shared-types/        # TS contracts shared by web and widget
├── infrastructure/          # Postgres init (runtime role bootstrap)
├── scripts/                 # Cross-platform dev scripts (smoke test)
├── docs/                    # PRD, architecture, database, API, security, roadmap, decisions, setup
├── .github/workflows/       # CI: lint, typecheck, tests, builds, Docker smoke test
└── docker-compose.yml       # Local stack: postgres, redis, migrate, api, worker, web
```

## Common commands

| Command | Purpose |
|---|---|
| `pnpm check` | All lint, typecheck and unit-test checks (TS + Python) |
| `pnpm dev:web` | Next.js with hot reload (against the Dockerized API) |
| `pnpm db:migrate` | Apply Alembic migrations |
| `pnpm smoke` | End-to-end checks against the running stack |

## Documentation

[PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) · [API spec](docs/API_SPEC.md) · [Security](docs/SECURITY.md) · [Roadmap](docs/ROADMAP.md) · [Decisions](docs/DECISIONS.md) · [Development setup](docs/DEVELOPMENT.md)
