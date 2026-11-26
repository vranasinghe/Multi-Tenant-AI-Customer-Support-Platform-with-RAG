#!/usr/bin/env bash
# One run of the unchanged strict capacity gate. No retries: a miss is a result to look at.
# The thresholds live in the test. See docs/DEVELOPMENT.md for what a pass here does and does
# not certify.
source "$(dirname "$0")/lib.sh"

status=0
compose exec -T -e AUDIT_OUTPUT_DIR=/tmp/ci/capacity api \
  pytest tests/integration/api/mvp_improvement/test_chat_capacity.py \
  -q --tb=short -p no:cacheprovider --junitxml=/tmp/ci/capacity.xml \
  2>&1 | grep -vE '\[(info|warning|debug|error)' | tee "$ARTIFACTS/capacity.log" || status=$?
compose cp api:/tmp/ci/capacity.xml "$ARTIFACTS/capacity.xml"
compose cp api:/tmp/ci/capacity "$ARTIFACTS/capacity-data"
nproc >"$ARTIFACTS/capacity-host.txt" 2>/dev/null || true
"$PYTHON" scripts/ci/check_junit.py "$ARTIFACTS/capacity.xml" --min-tests 4
exit "$status"
