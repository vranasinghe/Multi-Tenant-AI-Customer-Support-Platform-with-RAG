#!/usr/bin/env bash
# Build and (re)start the production stack. Run from the repo root on the VPS:
#     bash deploy/deploy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env.production"
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE (copy .env.production.example and fill it in)." >&2
  exit 1
fi
chmod 600 "$ENV_FILE"

if [ ! -f services/api/widget_assets/v1/loader.js ]; then
  echo "Missing services/api/widget_assets/v1/loader.js - build the widget first:" >&2
  echo "  corepack pnpm install && corepack pnpm --filter @acs/widget build" >&2
  exit 1
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml)

"${COMPOSE[@]}" build
"${COMPOSE[@]}" up -d --remove-orphans
"${COMPOSE[@]}" ps

SITE_HOST="$(grep -E '^SITE_HOST=' "$ENV_FILE" | cut -d= -f2-)"
echo
echo "Waiting for https://$SITE_HOST/readyz (first start also fetches the TLS certificate)..."
for _ in $(seq 1 30); do
  if curl -fsS "https://$SITE_HOST/readyz" >/dev/null 2>&1; then
    echo "Ready: https://$SITE_HOST"
    exit 0
  fi
  sleep 5
done
echo "Not ready yet. Check: ${COMPOSE[*]} logs --tail=100 caddy api" >&2
exit 1
