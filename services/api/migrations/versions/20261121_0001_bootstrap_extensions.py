"""Bootstrap database: extensions and tenant-context helper functions.

No business tables yet. Installs the extensions the data model relies on (docs/DATABASE.md)
and the `app` schema with the RLS helper functions used by every tenant policy from Phase 1.

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_app"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    # Transaction-local GUCs set per request/task; NULL when unset so RLS policies match nothing.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_org_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
          SELECT nullif(current_setting('app.current_org_id', true), '')::uuid
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS uuid
        LANGUAGE sql STABLE PARALLEL SAFE AS $$
          SELECT nullif(current_setting('app.current_user_id', true), '')::uuid
        $$
        """
    )
    # The runtime role is created by infrastructure (infrastructure/postgres); grant if present.
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT USAGE ON SCHEMA app TO {APP_ROLE};
            GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO {APP_ROLE};
          END IF;
        END
        $$
        """  # noqa: S608  # constant role name, no user input
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.current_user_id()")
    op.execute("DROP FUNCTION IF EXISTS app.current_org_id()")
    op.execute("DROP SCHEMA IF EXISTS app")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS citext")
    op.execute("DROP EXTENSION IF EXISTS vector")
