# API service

FastAPI backend and Celery workers. See [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md) for setup.

| Path | Purpose |
|---|---|
| `app/main.py` | App factory (`create_app`) and ASGI entrypoint |
| `app/core/` | Settings, logging, request context middleware, errors, DB and Redis clients |
| `app/api/` | HTTP routers (health now; versioned `/api/v1` routers later) |
| `app/schemas/` | Pydantic request/response models |
| `app/services/` | Use-case logic (readiness checks now) |
| `app/models/` | SQLAlchemy declarative base (no tables yet) |
| `app/rag/`, `app/integrations/` | Reserved for later phases |
| `app/workers/` | Celery app, signals, tasks |
| `app/cli.py` | Operational commands (`python -m app.cli check-worker`) |
| `migrations/` | Alembic migrations |
