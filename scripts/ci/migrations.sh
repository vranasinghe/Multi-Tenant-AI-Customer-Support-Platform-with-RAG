#!/usr/bin/env bash
# Migration integrity and tenant protection on the running stack's database. Upgrade, downgrade
# and data-preservation cases run on their own throwaway databases inside the test suite.
source "$(dirname "$0")/lib.sh"

run() { compose exec -T api "$@"; }

heads="$(run alembic heads | grep -c '(head)')"
head="$(run alembic heads | grep '(head)' | awk '{print $1}')"
current="$(run alembic current 2>/dev/null | grep '(head)' | awk '{print $1}')"
echo "heads=$heads head=$head current=$current" | tee "$ARTIFACTS/migrations.log"
[ "$heads" = 1 ]
[ -n "$head" ] && [ "$head" = "$current" ]
run python -m app.cli check-rls | tee -a "$ARTIFACTS/migrations.log"
# The whole chain stays reversible on an empty database (data cases: tests/integration).
run python - <<'PY' | tee -a "$ARTIFACTS/migrations.log"
import os

from alembic import command
from alembic.config import Config

from app.services.readiness import ALEMBIC_INI
from tests.support.database import temporary_database

with temporary_database() as database:
    os.environ["MIGRATION_DATABASE_URL"] = database.owner_url.render_as_string(hide_password=False)
    config = Config(str(ALEMBIC_INI))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
print("empty database: downgrade base and upgrade head OK")
PY
