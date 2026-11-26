# Git checkpoint plan (proposal; nothing committed or pushed)

## Current state

* Branch `cursor/phase-7-conversation-analytics-327e` at `db4d352` (same as `origin`). All
  remediation work since then is uncommitted: modified tracked files and new files.
* A full copy of the starting state of this final task is in
  `C:\Users\LENOVO\acs-snapshots\milestone-a-final-20261126\`: `worktree.tar.gz` (2,594 files,
  `inventory.sha256`), `tracked.patch`, `history.bundle`, `status.txt`. **`.env` is deliberately
  not in it.** To compare or recover, extract into an empty folder; do not extract over the repo.
* No other coding session was running on this repository when the work began.

## Changes that predate the remediation work

Recorded at the A4 preflight as already uncommitted: `.prettierignore`,
`apps/web/src/components/chatbots/answer-text.tsx`, `docker-compose.prod.yml`,
`packages/ui/src/styles/globals.css` and the untracked `docs/ui-ux/`. Treat these as **yours**:
commit them separately, or leave them out. `docker-compose.prod.yml` also carries later
remediation changes, so it needs a hunk-by-hunk look (`git add -p`).

## Proposed branch and commits

Create `milestone-a/stabilization` from the current branch, then, in this order. Grouping is by
area because several files were changed by more than one task, so one-commit-per-audit would need
risky hunk splitting.

| # | Subject | Paths |
|---|---|---|
| 0 | UI foundation changes made before remediation | `.prettierignore`, `answer-text.tsx`, `globals.css`, `docs/ui-ux/` (yours; confirm first) |
| 1 | Trusted proxy and runtime launcher (AUD-04) | `services/api/Dockerfile`, `app/server.py`, `app/core/proxy_trust.py`, `app/core/config.py`, proxy tests |
| 2 | Chat admission, cleanup and capacity (PERF-01) | `app/services/chat_controls.py`, `app/services/conversations.py`, `app/main.py`, their tests |
| 3 | Parser isolation, fencing and stored originals (AUD-05, A5.1) | `app/rag/`, `app/services/knowledge/`, `app/models/knowledge.py`, `app/workers/tasks/ingest.py`, ingestion tests and support files |
| 4 | Conversation inbox gaps (AUD-06) | `app/api/conversations.py`, `app/services/inbox.py`, `apps/web/src/components/conversations/`, `apps/web/src/lib/api/`, inbox tests |
| 5 | Widget lifecycle and public privacy (AUD-07) | `apps/widget/`, `services/api/widget_assets/`, `app/services/public_view.py`, `app/services/widget_chat.py`, `app/api/widget_*.py`, widget tests |
| 6 | Migration lint, downgrade guard, backup and restore (MIG-02) | `migrations/`, `app/core/data_check.py`, `app/cli.py`, `deploy/`, migration and fingerprint tests |
| 7 | Maintenance queue and scheduler health | `app/workers/celery_app.py`, `app/workers/health.py`, `docker-compose*.yml`, `package.json`, scheduler tests |
| 8 | CI workflows and scripts | `.github/workflows/`, `scripts/ci/`, `.env*.example` |
| 9 | Documentation | `docs/` except `evidence/` and `ui-ux/` |
| 10 | Evidence (optional) | `docs/mvp-improvement/evidence/`, `docs/mvp-improvement/tools/` |

Paths under `app/` mean `services/api/app/`. Some files serve two groups (`config.py`,
`conversations.py`, `celery_app.py`): intermediate commits are **not guaranteed to build or pass**.
Only the tip was validated. If every commit must pass, squash 1–9 into one.

## Before committing

* **Decide on evidence.** It is about 85 MB, includes screenshots and logs of synthetic data, and
  would stay in history permanently. A secret scan of it found no developer key; consider keeping
  it out of Git and archiving it elsewhere.
* Do not commit `.env`, `ci.env`, `ci-artifacts/` (the last two are not in `.gitignore`; add them
  if you run the CI scripts with output inside the repository) or `__pycache__`.
* `services/api/C:` is a stray local Ruff cache folder; Git does not track it. Delete it when
  convenient.
* The tracked build output is exactly `services/api/widget_assets/v1/loader.js` and
  `manifest.json`; they match a Linux build of the current sources.
* New shell scripts must stay LF (`.gitattributes` already enforces it). On Linux they are run
  with `bash`, so no executable bit is needed.
* Commit messages carry no AI attribution, per your instruction.

## Push

Pushing a branch and opening a pull request is what would run CI for the first time (CI-HOSTED).
Both need your explicit go-ahead.
