#!/usr/bin/env bash
# Backup of Postgres and uploaded documents. Run from anywhere:
#     bash deploy/backup.sh              # online (nightly)
#     QUIESCE=1 bash deploy/backup.sh    # writers and storage stopped: use before a migration
#
# Writes db-<stamp>.sql.gz, storage-<stamp>.tar.gz and <stamp>.sha256 to ~/backups (kept 7 days).
# Copy that folder OFF the server too (rclone to Backblaze B2 / Cloudflare R2 / Google Drive) -
# a backup on the same disk is not a backup. Keep .env.production separately and safely: it is
# not in the backup. Redis is not backed up; the sweeper re-queues jobs from the database.
#
# An online backup reads the database first and the files a little later, so an original removed
# in between is missing from the copy. QUIESCE=1 closes that window at the cost of downtime.
# See docs/RECOVERY.md.
#
# Cron (as the deploy user):  0 3 * * * cd ~/app && bash deploy/backup.sh >> ~/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1

ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT="${COMPOSE_PROJECT_NAME:-acs-prod}"
COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "${COMPOSE_FILE:-docker-compose.prod.yml}")
HELPER="${BACKUP_HELPER_IMAGE:-redis:8.10.3-alpine}" # any image with sh and tar
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true; }
DB_USER="$(env_value POSTGRES_USER)"
DB_NAME="$(env_value POSTGRES_DB)"

DEST="${BACKUP_DIR:-$HOME/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
umask 077
DEST="$(cd "$DEST" && pwd)"
# Docker needs a native path for a bind mount (Git Bash on Windows).
DEST_MOUNT="$(cd "$DEST" && (pwd -W 2>/dev/null || pwd))"

running=()
resume() {
  if [ "${#running[@]}" -gt 0 ]; then "${COMPOSE[@]}" start "${running[@]}"; fi
}
if [ "${QUIESCE:-0}" = 1 ]; then
  for service in $("${COMPOSE[@]}" ps --services --status running); do
    case "$service" in api | worker | maintenance | beat) running+=("$service") ;; esac
  done
  trap resume EXIT
  if [ "${#running[@]}" -gt 0 ]; then "${COMPOSE[@]}" stop "${running[@]}"; fi
fi

echo "Postgres dump -> $DEST/db-$STAMP.sql.gz"
"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U "${DB_USER:-platform_owner}" -d "${DB_NAME:-chatbot}" --no-owner \
  | gzip >"$DEST/db-$STAMP.sql.gz.partial"
mv "$DEST/db-$STAMP.sql.gz.partial" "$DEST/db-$STAMP.sql.gz"

echo "Documents volume -> $DEST/storage-$STAMP.tar.gz"
if [ "${QUIESCE:-0}" = 1 ]; then
  "${COMPOSE[@]}" stop storage
  running+=(storage)
fi
docker run --rm --network none --user 0 --entrypoint sh \
  -v "${PROJECT}_storagedata:/data:ro" -v "$DEST_MOUNT:/out" "$HELPER" \
  -c "tar czf '/out/storage-$STAMP.tar.gz.partial' -C /data ."
mv "$DEST/storage-$STAMP.tar.gz.partial" "$DEST/storage-$STAMP.tar.gz"

(cd "$DEST" && sha256sum "db-$STAMP.sql.gz" "storage-$STAMP.tar.gz" >"$STAMP.sha256")

find "$DEST" -type f \( -name 'db-*.sql.gz' -o -name 'storage-*.tar.gz' -o -name '*.sha256' \) \
  -mtime +7 -delete
echo "Done: $STAMP (restore with: bash deploy/restore.sh \"$DEST\" $STAMP)"
