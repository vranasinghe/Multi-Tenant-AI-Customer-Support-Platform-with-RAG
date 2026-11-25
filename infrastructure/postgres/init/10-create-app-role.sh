#!/bin/sh
# Runs once, on first initialisation of the local Postgres volume (docker-entrypoint-initdb.d).
# Creates the unprivileged runtime role used by the API and workers. The schema owner
# (POSTGRES_USER) runs migrations; the runtime role can only read/write data, so Postgres
# row-level security cannot be bypassed by application code (docs/DATABASE.md §4.1).
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v db_name="$POSTGRES_DB" \
  -v owner_user="$POSTGRES_USER" \
  -v app_user="$POSTGRES_APP_USER" \
  -v app_password="$POSTGRES_APP_PASSWORD" \
  -f /docker-entrypoint-initdb.d/sql/create-app-role.sql
