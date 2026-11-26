#!/usr/bin/env bash
# The whole backend suite inside the Linux api container: real services, real prefork workers
# (ingestion, crawl, maintenance), real object storage and the live ingestion path.
#
#   bash scripts/ci/backend-suite.sh [--with-capacity]
#
# The strict latency gate depends on the hardware, so it has its own job (capacity.sh) unless
# --with-capacity is given. The only skips accepted are the runtime proxy tests, which
# runtime-proxy.sh runs from the host.
source "$(dirname "$0")/lib.sh"

capacity=tests/integration/api/mvp_improvement/test_chat_capacity.py
select=(--ignore="$capacity")
if [ "${1:-}" = "--with-capacity" ]; then select=(); fi

status=0
# The live test speaks to the API as the web app: its origin follows the stack's web port.
compose exec -T -e LIVE_INGESTION=1 -e LIVE_ORIGIN="http://localhost:$(env_value WEB_HOST_PORT)" \
  -e AUDIT_OUTPUT_DIR=/tmp/ci/data api \
  pytest -q --tb=short -p no:cacheprovider --junitxml=/tmp/ci/backend.xml "${select[@]}" \
  2>&1 | grep -vE '\[(info|warning|debug|error)' | tee "$ARTIFACTS/backend.log" || status=$?
compose cp api:/tmp/ci/backend.xml "$ARTIFACTS/backend.xml"
"$PYTHON" scripts/ci/check_junit.py "$ARTIFACTS/backend.xml" --min-tests 1100 \
  --allow-skip tests.integration.test_runtime_proxy_trust
exit "$status"
