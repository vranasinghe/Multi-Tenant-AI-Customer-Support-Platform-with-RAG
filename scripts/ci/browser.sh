#!/usr/bin/env bash
# Smoke test and every Playwright journey against the running stack, including the web image.
#
#   bash scripts/ci/up.sh web && bash scripts/ci/browser.sh
#
# E2E_BROWSER_CHANNEL: "chrome" (default, installed Chrome) or empty for Playwright's Chromium.
# PNPM overrides the pnpm command (default: corepack pnpm).
source "$(dirname "$0")/lib.sh"

read -r -a pnpm <<<"${PNPM:-corepack pnpm}"
web="http://localhost:$(env_value WEB_HOST_PORT)"
api="http://localhost:$(env_value API_HOST_PORT)"

WEB_URL="$web" API_URL="$api" SMOKE_TIMEOUT_S=90 node scripts/smoke.mjs | tee "$ARTIFACTS/smoke.log"

status=0
(
  unset MSYS_NO_PATHCONV
  E2E_BASE_URL="$web" E2E_API_URL="$api" \
    E2E_MAILPIT_URL="http://127.0.0.1:$(env_value MAILPIT_UI_HOST_PORT)" \
    PLAYWRIGHT_JUNIT_OUTPUT_NAME="$ARTIFACTS/browser.xml" \
    "${pnpm[@]}" --filter @acs/web exec playwright test --reporter=list,junit --workers=1
) 2>&1 | tee "$ARTIFACTS/browser.log" || status=$?
grep -E '^ +[0-9]+ (skipped|flaky|did not run)' "$ARTIFACTS/browser.log" && status=1
exit "$status"
