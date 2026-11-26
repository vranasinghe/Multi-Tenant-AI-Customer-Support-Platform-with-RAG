# shellcheck shell=bash
# Shared by scripts/ci/*.sh. These start, fill and delete whole stacks, so they refuse to run
# unless the caller names a disposable one (see make-env.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

: "${COMPOSE_PROJECT_NAME:?set a disposable project name, for example acs-ci}"
: "${COMPOSE_ENV_FILES:?set the env file written by scripts/ci/make-env.sh}"
case "$COMPOSE_PROJECT_NAME" in
  ai-chatbot-saas | acs-prod)
    echo "refusing to run against the $COMPOSE_PROJECT_NAME stack" >&2
    exit 2
    ;;
esac
export COMPOSE_PROJECT_NAME COMPOSE_ENV_FILES
export MSYS_NO_PATHCONV=1 # Git Bash on Windows must not rewrite container paths

# How to run Python on the host (a developer without uv can point at the project venv).
PYTHON="${PYTHON:-python3}"
ARTIFACTS="${ARTIFACTS:-$ROOT/ci-artifacts}"
mkdir -p "$ARTIFACTS"
# Git Bash: host programs (Python, Node) need a Windows form of the path.
if command -v cygpath >/dev/null 2>&1; then ARTIFACTS="$(cygpath -m "$ARTIFACTS")"; fi

compose() { docker compose "$@"; }

env_value() { grep -E "^$1=" "$COMPOSE_ENV_FILES" | tail -n 1 | cut -d= -f2-; }
