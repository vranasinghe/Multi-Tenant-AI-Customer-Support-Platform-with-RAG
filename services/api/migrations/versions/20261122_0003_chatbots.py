"""Chatbots: per-organization assistant configuration (docs/DATABASE.md §3.3).

* Tenant table: ENABLE + FORCE RLS with the standard ``tenant_isolation`` policy.
* ``UNIQUE (org_id, id)`` so future child tables (knowledge sources, domains, conversations) can
  reference ``(org_id, chatbot_id)`` and the database itself rejects cross-tenant references.
* Names are unique per organization among non-deleted chatbots (case-insensitive).
* CHECK constraints mirror the API validation so no other write path can store bad config.
* Soft delete (``deleted_at``); the public key of a deleted chatbot never resolves again.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.core.rls import enable_tenant_rls_statements

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_app"


def _run(*statements: str) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _run(
        """
        CREATE TABLE chatbots (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
          name text NOT NULL,
          description text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          public_key text NOT NULL,
          instructions text NOT NULL DEFAULT '',
          tone text NOT NULL DEFAULT 'professional',
          response_length text NOT NULL DEFAULT 'balanced',
          welcome_message text NOT NULL DEFAULT '',
          fallback_message text NOT NULL DEFAULT '',
          language_mode text NOT NULL DEFAULT 'auto',
          language text,
          model text NOT NULL,
          temperature numeric(3, 2) NOT NULL DEFAULT 0.20,
          max_output_tokens integer NOT NULL DEFAULT 600,
          strict_grounding boolean NOT NULL DEFAULT true,
          show_sources boolean NOT NULL DEFAULT true,
          retrieval_top_k integer NOT NULL DEFAULT 6,
          widget_settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by uuid REFERENCES users (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz,
          CONSTRAINT uq_chatbots_org_id_id UNIQUE (org_id, id),
          CONSTRAINT uq_chatbots_public_key UNIQUE (public_key),
          CONSTRAINT ck_chatbots_name_length CHECK (char_length(name) BETWEEN 1 AND 80),
          CONSTRAINT ck_chatbots_description_length CHECK (char_length(description) <= 500),
          CONSTRAINT ck_chatbots_status
            CHECK (status IN ('draft', 'active', 'paused', 'archived')),
          CONSTRAINT ck_chatbots_instructions_length CHECK (char_length(instructions) <= 4000),
          CONSTRAINT ck_chatbots_tone
            CHECK (tone IN ('professional', 'friendly', 'concise', 'custom')),
          CONSTRAINT ck_chatbots_response_length
            CHECK (response_length IN ('concise', 'balanced', 'detailed')),
          CONSTRAINT ck_chatbots_welcome_length CHECK (char_length(welcome_message) <= 500),
          CONSTRAINT ck_chatbots_fallback_length CHECK (char_length(fallback_message) <= 500),
          CONSTRAINT ck_chatbots_language_mode CHECK (language_mode IN ('auto', 'fixed')),
          CONSTRAINT ck_chatbots_language_required
            CHECK (language_mode = 'auto' OR language IS NOT NULL),
          CONSTRAINT ck_chatbots_temperature CHECK (temperature BETWEEN 0 AND 1),
          CONSTRAINT ck_chatbots_max_output_tokens CHECK (max_output_tokens BETWEEN 64 AND 4096),
          CONSTRAINT ck_chatbots_retrieval_top_k CHECK (retrieval_top_k BETWEEN 1 AND 12),
          CONSTRAINT ck_chatbots_public_key_format CHECK (public_key ~ '^pk_live_[A-Za-z0-9]{24}$')
        )
        """,
        "CREATE INDEX ix_chatbots_org ON chatbots (org_id, created_at DESC) "
        "WHERE deleted_at IS NULL",
        "CREATE UNIQUE INDEX uq_chatbots_org_name_active ON chatbots (org_id, lower(name)) "
        "WHERE deleted_at IS NULL",
        "CREATE TRIGGER trg_chatbots_touch BEFORE UPDATE ON chatbots "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()",
    )
    _run(*enable_tenant_rls_statements("chatbots"))
    _run(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE ON chatbots TO {APP_ROLE};
            REVOKE DELETE, TRUNCATE ON chatbots FROM {APP_ROLE};
          END IF;
        END
        $$
        """  # noqa: S608  # constant identifiers, no user input
    )


def downgrade() -> None:
    _run("DROP TABLE IF EXISTS chatbots")
