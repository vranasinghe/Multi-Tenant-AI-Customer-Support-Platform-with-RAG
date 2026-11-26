#!/usr/bin/env bash
# Back up the running stack with deploy/backup.sh, restore it with deploy/restore.sh into a new,
# empty project, and prove the copy is the same: rows, vectors, protections, stored originals and
# what a signed-in user reads. Both projects are disposable (see lib.sh).
#
#   bash scripts/ci/up.sh && bash scripts/ci/restore-rehearsal.sh
source "$(dirname "$0")/lib.sh"

source_project="$COMPOSE_PROJECT_NAME"
restore_project="${source_project}-restore"
work="$ARTIFACTS/restore"
mkdir -p "$work"
backups="$(mktemp -d)"
export COMPOSE_FILE=docker-compose.yml ENV_FILE="$COMPOSE_ENV_FILES"

cleanup() {
  docker compose -p "$restore_project" down -v >/dev/null 2>&1 || true
  rm -rf "$backups"
  docker compose -p "$source_project" start >/dev/null 2>&1 || true
}
trap cleanup EXIT

state="$(compose exec -T api python -m tests.support.restore_probe seed | grep '^STATE ' | cut -c7-)"
[ -n "$state" ]

# Writers stopped: the fingerprint and the backup describe the same moment.
compose stop api worker maintenance beat
compose run --rm --no-deps -T api python -m app.cli verify-data >"$work/source.json"
started=$(date +%s)
QUIESCE=1 BACKUP_DIR="$backups" bash deploy/backup.sh | tee "$work/backup.log"
backup_seconds=$(($(date +%s) - started))
stamp="$(basename "$backups"/*.sha256 .sha256)"
compose stop

started=$(date +%s)
COMPOSE_PROJECT_NAME="$restore_project" bash deploy/restore.sh "$backups" "$stamp" |
  tee "$work/restore.log"
docker compose -p "$restore_project" up -d --wait --wait-timeout 300 api worker maintenance
docker compose -p "$restore_project" run --rm --no-deps -T api python -m app.cli verify-data \
  >"$work/restored.json"
restore_seconds=$(($(date +%s) - started))

if ! diff "$work/source.json" "$work/restored.json"; then
  echo "the restored data or its protections differ from the source" >&2
  exit 1
fi
echo "fingerprints identical"
docker compose -p "$restore_project" exec -T api python -m tests.support.restore_probe check "$state" |
  tee "$work/application.log"

# A second restore onto the now populated project must change nothing and fail.
if COMPOSE_PROJECT_NAME="$restore_project" bash deploy/restore.sh "$backups" "$stamp" \
  >"$work/refused.log" 2>&1; then
  echo "restore.sh overwrote a populated database" >&2
  exit 1
fi
grep -q refusing "$work/refused.log"

"$PYTHON" - "$work/source.json" "$backup_seconds" "$restore_seconds" <<'PY' | tee "$work/summary.log"
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
rows = {name: table["rows"] for name, table in report["tables"].items() if table["rows"]}
print(f"revision={report['revision']} objects={report['objects']['referenced']} rows={rows}")
print(f"backup_seconds={sys.argv[2]} restore_and_verify_seconds={sys.argv[3]}")
PY
echo "restore rehearsal passed"
