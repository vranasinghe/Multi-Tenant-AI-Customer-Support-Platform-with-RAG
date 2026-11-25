"""Tenant-scoped chat, widget credentials and durable usage reservations.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import enable_tenant_rls_statements

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("conversations", "messages", "widget_sessions", "chat_usage")


def upgrade() -> None:
    op.execute("""
      CREATE TABLE conversations (
        id uuid PRIMARY KEY, org_id uuid NOT NULL,
        chatbot_id uuid NOT NULL, channel text NOT NULL DEFAULT 'playground',
        created_by uuid REFERENCES users(id) ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(org_id, id),
        FOREIGN KEY(org_id, chatbot_id) REFERENCES chatbots(org_id, id) ON DELETE CASCADE,
        CHECK(channel IN ('playground', 'widget'))
      )
    """)
    op.execute("""
      CREATE TABLE messages (
        id uuid PRIMARY KEY, org_id uuid NOT NULL, conversation_id uuid NOT NULL,
        role text NOT NULL CHECK(role IN ('user', 'assistant')),
        content text NOT NULL DEFAULT '', status text NOT NULL DEFAULT 'complete'
          CHECK(status IN ('complete', 'streaming', 'interrupted', 'failed', 'fallback')),
        citations jsonb NOT NULL DEFAULT '[]',
        input_tokens integer NOT NULL DEFAULT 0 CHECK(input_tokens >= 0),
        output_tokens integer NOT NULL DEFAULT 0 CHECK(output_tokens >= 0),
        estimated_cost_usd numeric(18,8) NOT NULL DEFAULT 0 CHECK(estimated_cost_usd >= 0),
        usage_estimated boolean NOT NULL DEFAULT true, error_code text,
        feedback integer CHECK(feedback IN (-1, 1)),
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(org_id, id),
        FOREIGN KEY(org_id, conversation_id) REFERENCES conversations(org_id,id) ON DELETE CASCADE
      )
    """)
    op.execute(
        "CREATE INDEX ix_messages_conversation ON messages(org_id,conversation_id,created_at,id)"
    )
    op.execute(
        "CREATE INDEX ix_conversations_org ON conversations(org_id,chatbot_id,created_at DESC)"
    )
    op.execute("""
      CREATE TABLE widget_sessions (
        id uuid PRIMARY KEY, org_id uuid NOT NULL, chatbot_id uuid NOT NULL,
        conversation_id uuid NOT NULL, token_hash text NOT NULL UNIQUE,
        public_key text NOT NULL, expires_at timestamptz NOT NULL,
        message_count integer NOT NULL DEFAULT 0 CHECK(message_count >= 0),
        FOREIGN KEY(org_id,chatbot_id) REFERENCES chatbots(org_id,id) ON DELETE CASCADE,
        FOREIGN KEY(org_id,conversation_id) REFERENCES conversations(org_id,id) ON DELETE CASCADE
      )
    """)
    op.execute("""
      CREATE TABLE chat_usage (
        id uuid PRIMARY KEY, org_id uuid NOT NULL, conversation_id uuid NOT NULL,
        model text NOT NULL, period text NOT NULL,
        charged_tokens integer NOT NULL CHECK(charged_tokens >= 0),
        estimated_cost_usd numeric(18,8) NOT NULL CHECK(estimated_cost_usd >= 0),
        state text NOT NULL DEFAULT 'reserved' CHECK(state IN ('reserved','settled')),
        created_at timestamptz NOT NULL DEFAULT now(),
        FOREIGN KEY(org_id,conversation_id) REFERENCES conversations(org_id,id) ON DELETE CASCADE
      )
    """)
    op.execute("CREATE INDEX ix_chat_usage_period ON chat_usage(org_id,period)")
    for table in TABLES:
        for statement in enable_tenant_rls_statements(table):
            op.execute(statement)
        # Match the existing ingestion migration's owner inspection policy for fixtures/ops.
        op.execute(f"""DO $$ BEGIN EXECUTE format(
          'CREATE POLICY owner_read ON {table} FOR SELECT TO %I USING (true)', current_user);
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
            GRANT SELECT, INSERT, UPDATE ON {table} TO platform_app;
            REVOKE DELETE, TRUNCATE ON {table} FROM platform_app;
          END IF; END $$""")  # noqa: S608


def downgrade() -> None:
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE {table}")
