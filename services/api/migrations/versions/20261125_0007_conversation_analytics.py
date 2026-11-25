"""Conversation inbox, first-class events, analytics rollups and retention.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op

from app.core.rls import enable_tenant_rls_statements

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_app"
TABLES = (
    "conversation_events",
    "unanswered_questions",
    "analytics_daily",
    "conversation_exports",
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversations
          ADD COLUMN status text NOT NULL DEFAULT 'open',
          ADD COLUMN last_message_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN preview text NOT NULL DEFAULT '',
          ADD COLUMN satisfaction_score smallint,
          ADD COLUMN satisfaction_comment text,
          ADD COLUMN handoff_status text,
          ADD COLUMN handoff_reason text,
          ADD COLUMN handoff_contact text,
          ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()
        """
    )
    op.execute(
        """
        ALTER TABLE conversations
          ADD CONSTRAINT ck_conversations_status
            CHECK (status IN ('open', 'resolved', 'unresolved', 'handed_off')),
          ADD CONSTRAINT ck_conversations_satisfaction_score
            CHECK (satisfaction_score IS NULL OR satisfaction_score BETWEEN 1 AND 5),
          ADD CONSTRAINT ck_conversations_handoff_status
            CHECK (handoff_status IS NULL OR handoff_status IN
              ('requested', 'acknowledged', 'completed', 'cancelled'))
        """
    )
    op.execute(
        """
        UPDATE conversations c SET
          last_message_at = COALESCE(
            (SELECT max(m.created_at) FROM messages m
              WHERE m.org_id = c.org_id AND m.conversation_id = c.id),
            c.created_at
          ),
          preview = COALESCE(
            (SELECT left(m.content, 180) FROM messages m
              WHERE m.org_id = c.org_id AND m.conversation_id = c.id AND m.role = 'user'
              ORDER BY m.created_at, m.id LIMIT 1),
            ''
          )
        """
    )
    op.execute(
        "CREATE INDEX ix_conversations_inbox ON conversations (org_id, last_message_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX ix_conversations_status ON conversations (org_id, status, last_message_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_conversations_channel ON conversations (org_id, channel, last_message_at DESC)"
    )

    op.execute("ALTER TABLE messages ADD COLUMN latency_ms integer")
    op.execute(
        "ALTER TABLE messages ADD CONSTRAINT ck_messages_latency_ms CHECK (latency_ms IS NULL OR latency_ms >= 0)"
    )
    op.execute("CREATE INDEX ix_messages_content_trgm ON messages USING gin (content gin_trgm_ops)")

    # Keep usage after conversation deletion (analytics/cost history). MATCH SIMPLE would
    # otherwise NULL org_id on a composite ON DELETE SET NULL.
    op.execute("ALTER TABLE chat_usage DROP CONSTRAINT chat_usage_org_id_conversation_id_fkey")

    op.execute(
        """
        CREATE TABLE conversation_events (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          conversation_id uuid,
          chatbot_id uuid NOT NULL,
          kind text NOT NULL CHECK (kind IN (
            'status_changed', 'satisfaction_submitted', 'handoff_requested',
            'handoff_updated', 'unanswered_recorded'
          )),
          payload jsonb NOT NULL DEFAULT '{}',
          actor_type text NOT NULL CHECK (actor_type IN ('user', 'customer', 'system')),
          actor_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (org_id, id),
          FOREIGN KEY (org_id, chatbot_id) REFERENCES chatbots(org_id, id) ON DELETE CASCADE
        )
        """
    )
    # No FK to conversations: composite ON DELETE SET NULL would null org_id (NOT NULL).
    # Rows are kept after transcript delete so analytics still have the event.
    op.execute(
        "CREATE INDEX ix_conversation_events_org ON conversation_events (org_id, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE unanswered_questions (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          conversation_id uuid,
          chatbot_id uuid NOT NULL,
          message_id uuid,
          question text NOT NULL,
          normalized_question text NOT NULL,
          cluster_key text NOT NULL,
          channel text NOT NULL,
          reason text NOT NULL CHECK (reason IN (
            'insufficient_evidence', 'marked_unanswered', 'ambiguous_query', 'provider_failure'
          )),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (org_id, id),
          FOREIGN KEY (org_id, chatbot_id) REFERENCES chatbots(org_id, id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_unanswered_cluster
          ON unanswered_questions (org_id, chatbot_id, cluster_key, created_at DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE analytics_daily (
          org_id uuid NOT NULL,
          chatbot_id uuid NOT NULL,
          day date NOT NULL,
          channel text NOT NULL,
          conversations integer NOT NULL DEFAULT 0 CHECK (conversations >= 0),
          messages_user integer NOT NULL DEFAULT 0 CHECK (messages_user >= 0),
          messages_assistant integer NOT NULL DEFAULT 0 CHECK (messages_assistant >= 0),
          grounded_answers integer NOT NULL DEFAULT 0 CHECK (grounded_answers >= 0),
          ungrounded_answers integer NOT NULL DEFAULT 0 CHECK (ungrounded_answers >= 0),
          feedback_up integer NOT NULL DEFAULT 0 CHECK (feedback_up >= 0),
          feedback_down integer NOT NULL DEFAULT 0 CHECK (feedback_down >= 0),
          resolved integer NOT NULL DEFAULT 0 CHECK (resolved >= 0),
          unresolved integer NOT NULL DEFAULT 0 CHECK (unresolved >= 0),
          handed_off integer NOT NULL DEFAULT 0 CHECK (handed_off >= 0),
          csat_submitted integer NOT NULL DEFAULT 0 CHECK (csat_submitted >= 0),
          csat_positive integer NOT NULL DEFAULT 0 CHECK (csat_positive >= 0),
          unanswered integer NOT NULL DEFAULT 0 CHECK (unanswered >= 0),
          prompt_tokens bigint NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
          completion_tokens bigint NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
          charged_tokens bigint NOT NULL DEFAULT 0 CHECK (charged_tokens >= 0),
          cost_usd numeric(18, 8) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
          latency_p95_ms integer,
          PRIMARY KEY (org_id, chatbot_id, day, channel)
        )
        """
    )
    op.execute("CREATE INDEX ix_analytics_daily_org_day ON analytics_daily (org_id, day)")

    op.execute(
        """
        CREATE TABLE conversation_exports (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          created_by uuid REFERENCES users(id) ON DELETE SET NULL,
          status text NOT NULL DEFAULT 'ready'
            CHECK (status IN ('pending', 'ready', 'failed')),
          row_count integer NOT NULL DEFAULT 0 CHECK (row_count >= 0),
          storage_key text NOT NULL,
          error_code text,
          created_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          UNIQUE (org_id, id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_conversation_exports_org ON conversation_exports (org_id, created_at DESC)"
    )

    for table in TABLES:
        for statement in enable_tenant_rls_statements(table):
            op.execute(statement)

    tables = ", ".join(TABLES)
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {APP_ROLE};
            GRANT DELETE ON conversations, messages, widget_sessions TO {APP_ROLE};
          END IF;
        END
        $$
        """  # noqa: S608
    )

    op.execute(
        """
        CREATE FUNCTION app.list_orgs_for_conversation_jobs()
        RETURNS TABLE (org_id uuid, retention_days integer)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT o.id,
                 COALESCE((o.settings->>'conversation_retention_days')::integer, 365)
          FROM public.organizations o
          WHERE o.deleted_at IS NULL
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.list_orgs_for_conversation_jobs() FROM PUBLIC")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT EXECUTE ON FUNCTION app.list_orgs_for_conversation_jobs() TO {APP_ROLE};
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.list_orgs_for_conversation_jobs()")
    for table in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute(
        """
        ALTER TABLE chat_usage
          ADD CONSTRAINT chat_usage_org_id_conversation_id_fkey
          FOREIGN KEY (org_id, conversation_id)
          REFERENCES conversations(org_id, id) ON DELETE CASCADE
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_messages_content_trgm")
    op.execute("ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_latency_ms")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS latency_ms")
    op.execute("DROP INDEX IF EXISTS ix_conversations_channel")
    op.execute("DROP INDEX IF EXISTS ix_conversations_status")
    op.execute("DROP INDEX IF EXISTS ix_conversations_inbox")
    op.execute(
        """
        ALTER TABLE conversations
          DROP CONSTRAINT IF EXISTS ck_conversations_handoff_status,
          DROP CONSTRAINT IF EXISTS ck_conversations_satisfaction_score,
          DROP CONSTRAINT IF EXISTS ck_conversations_status,
          DROP COLUMN IF EXISTS updated_at,
          DROP COLUMN IF EXISTS handoff_contact,
          DROP COLUMN IF EXISTS handoff_reason,
          DROP COLUMN IF EXISTS handoff_status,
          DROP COLUMN IF EXISTS satisfaction_comment,
          DROP COLUMN IF EXISTS satisfaction_score,
          DROP COLUMN IF EXISTS preview,
          DROP COLUMN IF EXISTS last_message_at,
          DROP COLUMN IF EXISTS status
        """
    )
