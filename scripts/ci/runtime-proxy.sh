#!/usr/bin/env bash
# Build the production runtime image and run the proxy trust tests against it (AUD-04). They drive
# Docker from the host, so the full suite inside the api container has to skip them.
#
#   HOST_PYTHON=<project venv python> bash scripts/ci/runtime-proxy.sh
#
# Needs a running stack (up.sh) for the migrated database and Redis.
source "$(dirname "$0")/lib.sh"

image="${RUNTIME_IMAGE:-acs-api:ci-runtime}"
host_python="${HOST_PYTHON:-$ROOT/services/api/.venv/bin/python}"

docker build --target runtime -t "$image" services/api
# The image must hold the widget bundle that is committed.
docker run --rm --network none "$image" cat widget_assets/v1/loader.js |
  cmp - services/api/widget_assets/v1/loader.js

export RUNTIME_PROXY_IMAGE="$image"
export RUNTIME_PROXY_STACK_NETWORK="${COMPOSE_PROJECT_NAME}_default"
RUNTIME_PROXY_REDIS_CONTAINER="$(compose ps -q redis)"
export RUNTIME_PROXY_REDIS_CONTAINER
export RUNTIME_PROXY_DATABASE_URL="postgresql+psycopg://$(env_value POSTGRES_APP_USER):$(env_value POSTGRES_APP_PASSWORD)@postgres:5432/$(env_value POSTGRES_DB)"

status=0
(cd services/api && "$host_python" -m pytest tests/integration/test_runtime_proxy_trust.py \
  -q --tb=short -p no:cacheprovider --junitxml="$ARTIFACTS/runtime-proxy.xml") |
  tee "$ARTIFACTS/runtime-proxy.log" || status=$?
"$PYTHON" scripts/ci/check_junit.py "$ARTIFACTS/runtime-proxy.xml" --min-tests 17
exit "$status"
