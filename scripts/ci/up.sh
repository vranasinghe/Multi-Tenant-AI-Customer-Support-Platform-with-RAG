#!/usr/bin/env bash
# Start the disposable stack and wait until every service with a health check is healthy.
#   bash scripts/ci/up.sh [extra services, e.g. web]
source "$(dirname "$0")/lib.sh"
compose up -d --build --wait --wait-timeout 400 api worker maintenance beat "$@"
compose ps --format '{{.Service}} {{.Status}}'
