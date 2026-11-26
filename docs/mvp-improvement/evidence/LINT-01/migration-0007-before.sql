BEGIN;

-- Running upgrade 0006 -> 0007

ALTER TABLE conversations
          ADD COLUMN status text NOT NULL DEFAULT 'open',
          ADD COLUMN last_message_at timestamptz NOT NULL DEFAULT now(),
          ADD COLUMN preview text NOT NULL DEFAULT '',
          ADD COLUMN satisfaction_score smallint,
          ADD COLUMN satisfaction_comment text,
          ADD COLUMN handoff_status text,
          ADD COLUMN handoff_reason text,
          ADD COLUMN handoff_contact text,
          ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE conversations
          ADD CONSTRAINT ck_conversations_status
            CHECK (status IN ('open', 'resolved', 'unresolved', 'handed_off')),
          ADD CONSTRAINT ck_conversations_satisfaction_score
            CHECK (satisfaction_score IS NULL OR satisfaction_score BETWEEN 1 AND 5),
          ADD CONSTRAINT ck_conversations_handoff_status
            CHECK (handoff_status IS NULL OR handoff_status IN
              ('requested', 'acknowledged', 'completed', 'cancelled'));

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
          );

CREATE INDEX ix_conversations_inbox ON conversations (org_id, last_message_at DESC, id DESC);

CREATE INDEX ix_conversations_status ON conversations (org_id, status, last_message_at DESC);

CREATE INDEX ix_conversations_channel ON conversations (org_id, channel, last_message_at DESC);

ALTER TABLE messages ADD COLUMN latency_ms integer;

ALTER TABLE messages ADD CONSTRAINT ck_messages_latency_ms CHECK (latency_ms IS NULL OR latency_ms >= 0);

CREATE INDEX ix_messages_content_trgm ON messages USING gin (content gin_trgm_ops);

ALTER TABLE chat_usage DROP CONSTRAINT chat_usage_org_id_conversation_id_fkey;

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
        );

CREATE INDEX ix_conversation_events_org ON conversation_events (org_id, created_at DESC);

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
        );

CREATE INDEX ix_unanswered_cluster
          ON unanswered_questions (org_id, chatbot_id, cluster_key, created_at DESC);

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
        );

CREATE INDEX ix_analytics_daily_org_day ON analytics_daily (org_id, day);

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
        );

CREATE INDEX ix_conversation_exports_org ON conversation_exports (org_id, created_at DESC);

ALTER TABLE conversation_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE conversation_events FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON conversation_events USING (org_id = app.current_org_id()) WITH CHECK (org_id = app.current_org_id());

ALTER TABLE unanswered_questions ENABLE ROW LEVEL SECURITY;

ALTER TABLE unanswered_questions FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON unanswered_questions USING (org_id = app.current_org_id()) WITH CHECK (org_id = app.current_org_id());

ALTER TABLE analytics_daily ENABLE ROW LEVEL SECURITY;

ALTER TABLE analytics_daily FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON analytics_daily USING (org_id = app.current_org_id()) WITH CHECK (org_id = app.current_org_id());

ALTER TABLE conversation_exports ENABLE ROW LEVEL SECURITY;

ALTER TABLE conversation_exports FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON conversation_exports USING (org_id = app.current_org_id()) WITH CHECK (org_id = app.current_org_id());

DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON conversation_events, unanswered_questions, analytics_daily, conversation_exports TO platform_app;
            GRANT DELETE ON conversations, messages, widget_sessions TO platform_app;
          END IF;
        END
        $$;

CREATE FUNCTION app.list_orgs_for_conversation_jobs()
        RETURNS TABLE (org_id uuid, retention_days integer)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT o.id,
                 COALESCE((o.settings->>'conversation_retention_days')::integer, 365)
          FROM public.organizations o
          WHERE o.deleted_at IS NULL
        $$;

REVOKE ALL ON FUNCTION app.list_orgs_for_conversation_jobs() FROM PUBLIC;

DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'platform_app') THEN
            GRANT EXECUTE ON FUNCTION app.list_orgs_for_conversation_jobs() TO platform_app;
          END IF;
        END
        $$;

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

COMMIT;

BEGIN;

-- Running downgrade 0007 -> 0006

DROP FUNCTION IF EXISTS app.list_orgs_for_conversation_jobs();

DROP TABLE IF EXISTS conversation_exports;

DROP TABLE IF EXISTS analytics_daily;

DROP TABLE IF EXISTS unanswered_questions;

DROP TABLE IF EXISTS conversation_events;

ALTER TABLE chat_usage
          ADD CONSTRAINT chat_usage_org_id_conversation_id_fkey
          FOREIGN KEY (org_id, conversation_id)
          REFERENCES conversations(org_id, id) ON DELETE CASCADE;

DROP INDEX IF EXISTS ix_messages_content_trgm;

ALTER TABLE messages DROP CONSTRAINT IF EXISTS ck_messages_latency_ms;

ALTER TABLE messages DROP COLUMN IF EXISTS latency_ms;

DROP INDEX IF EXISTS ix_conversations_channel;

DROP INDEX IF EXISTS ix_conversations_status;

DROP INDEX IF EXISTS ix_conversations_inbox;

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
          DROP COLUMN IF EXISTS status;

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0007';

COMMIT;

