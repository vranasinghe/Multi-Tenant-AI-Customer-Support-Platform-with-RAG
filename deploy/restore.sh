#!/usr/bin/env bash
# Restore one backup into an EMPTY stack (new volumes):
#     bash deploy/restore.sh ~/backups <stamp>
#
# It refuses a database that has tables or a document volume that has files, so it cannot
# overwrite a running system. To replace one, restore into a new Compose project name, verify,
# then switch (docs/RECOVERY.md).
set -euo pipefail
export MSYS_NO_PATHCONV=1

SOURCE="$(cd "${1:?usage: restore.sh <backup dir> <stamp>}" && pwd)"
STAMP="${2:?usage: restore.sh <backup dir> <stamp>}"
SOURCE_MOUNT="$(cd "$SOURCE" && (pwd -W 2>/dev/null || pwd))"
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env.production}"
PROJECT="${COMPOSE_PROJECT_NAME:-acs-prod}"
COMPOSE=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "${COMPOSE_FILE:-docker-compose.prod.yml}")
HELPER="${BACKUP_HELPER_IMAGE:-redis:8.10.3-alpine}"
env_value() { grep -E "^$1=" "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true; }
DB_USER="$(env_value POSTGRES_USER)"
DB_USER="${DB_USER:-platform_owner}"
DB_NAME="$(env_value POSTGRES_DB)"
DB_NAME="${DB_NAME:-chatbot}"
APP_USER="$(env_value POSTGRES_APP_USER)"
APP_USER="${APP_USER:-platform_app}"

(cd "$SOURCE" && sha256sum -c "$STAMP.sha256")

# Creates the volume, and on a new one the unprivileged runtime role (infrastructure/postgres/init).
"${COMPOSE[@]}" up -d --wait postgres
tables="$("${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -tAc \
  "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")"
if [ "$tables" != 0 ]; then
  echo "refusing: database $DB_NAME already has $tables tables" >&2
  exit 1
fi
# A new volume starts with the image's own `.rustfs` folder; anything else is stored data.
"${COMPOSE[@]}" create storage
docker run --rm --network none --user 0 --entrypoint sh \
  -v "${PROJECT}_storagedata:/data" -v "$SOURCE_MOUNT:/in:ro" "$HELPER" \
  -c "if [ -n \"\$(ls -A /data | grep -vx '.rustfs')\" ]; then echo 'refusing: the document volume is not empty' >&2; exit 1; fi; tar xzf '/in/storage-$STAMP.tar.gz' -C /data"

# A new database grants the application role every DML right on each table created
# (infrastructure/postgres/init). A dump only ever adds grants, so rights the source had taken
# away would come back. Remove those defaults first; the dump restores the source's own.
"${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" --quiet --set ON_ERROR_STOP=1   --set owner="$DB_USER" --set app="${APP_USER}" <<'SQL'
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public REVOKE ALL ON TABLES FROM :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public REVOKE ALL ON SEQUENCES FROM :"app";
SQL

# All or nothing: the first error stops it and nothing is kept.
gunzip -c "$SOURCE/db-$STAMP.sql.gz" |
  "${COMPOSE[@]}" exec -T postgres \
    psql -U "$DB_USER" -d "$DB_NAME" --quiet --set ON_ERROR_STOP=1 --single-transaction >/dev/null

echo "Restored $STAMP into project $PROJECT. Start the stack and verify before using it:"
echo "  ${COMPOSE[*]} up -d && ${COMPOSE[*]} exec -T api python -m app.cli verify-data"
