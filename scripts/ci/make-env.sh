#!/usr/bin/env bash
# Write a throwaway Compose env file with synthetic credentials and offline providers.
#
#   bash scripts/ci/make-env.sh <file> [port-offset]
#
# demo LLM and hash embeddings only: no provider key is read, written or needed. The port offset
# moves every published port so a disposable stack never collides with a developer one.
set -euo pipefail

out="${1:?usage: make-env.sh <file> [port-offset]}"
offset="${2:-0}"
secret() { od -An -N18 -tx1 /dev/urandom | tr -d ' \n'; }

owner="$(secret)"
app="$(secret)"
storage="$(secret)"
web_port=$((3000 + offset))
api_port=$((8000 + offset))

umask 077
cat >"$out" <<EOF
APP_ENV=local
LOG_LEVEL=INFO
LOG_FORMAT=console
POSTGRES_DB=chatbot
POSTGRES_USER=platform_owner
POSTGRES_PASSWORD=ci-owner-$owner
POSTGRES_APP_USER=platform_app
POSTGRES_APP_PASSWORD=ci-app-$app
S3_BUCKET=acs-documents
S3_ACCESS_KEY=ci_storage
S3_SECRET_KEY=ci-storage-$storage
POSTGRES_HOST_PORT=$((55432 + offset))
REDIS_HOST_PORT=$((6379 + offset))
API_HOST_PORT=$api_port
WEB_HOST_PORT=$web_port
MAILPIT_UI_HOST_PORT=$((8025 + offset))
MAILPIT_SMTP_HOST_PORT=$((1025 + offset))
STORAGE_HOST_PORT=$((9000 + offset))
CORS_ALLOWED_ORIGINS=http://localhost:$web_port
NEXT_PUBLIC_API_URL=http://localhost:$api_port
EMBEDDING_PROVIDER=hash
EMBEDDING_MODEL=hash-v1
EMBEDDING_API_KEY=
LLM_PROVIDER=demo
LLM_API_KEY=
EOF
echo "wrote $out (ports offset by $offset)"
