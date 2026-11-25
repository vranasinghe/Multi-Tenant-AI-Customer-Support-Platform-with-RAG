#!/usr/bin/env bash
# Nightly backup of Postgres and uploaded documents. Run from the repo root:
#     bash deploy/backup.sh
# Writes to ~/backups (kept 7 days). Copy that folder OFF the server too (rclone to
# Backblaze B2 / Cloudflare R2 / Google Drive) - a backup on the same disk is not a backup.
#
# Cron (as the deploy user):  0 3 * * * cd ~/app && bash deploy/backup.sh >> ~/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose --env-file .env.production -f docker-compose.prod.yml)
set -a; . ./.env.production; set +a

DEST="${BACKUP_DIR:-$HOME/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"

echo "Postgres dump -> $DEST/db-$STAMP.sql.gz"
"${COMPOSE[@]}" exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-platform_owner}" -d "${POSTGRES_DB:-chatbot}" --no-owner \
  | gzip > "$DEST/db-$STAMP.sql.gz"

echo "Documents volume -> $DEST/storage-$STAMP.tar.gz"
docker run --rm -v acs-prod_storagedata:/data:ro -v "$DEST":/out alpine \
  tar czf "/out/storage-$STAMP.tar.gz" -C /data .

find "$DEST" -type f \( -name 'db-*.sql.gz' -o -name 'storage-*.tar.gz' \) -mtime +7 -delete
echo "Done."
