"""Knowledge: sources, documents, chunks (pgvector), ingestion jobs, storage-deletion outbox.

Isolation (docs/DATABASE.md §3.4, §4):

* Every table carries ``org_id`` with ENABLE + FORCE RLS and the standard ``tenant_isolation``
  policy, so a request/worker whose ``app.current_org_id`` is org A can never read or write org B.
* Children reference ``(org_id, parent_id)`` composite keys, so the database itself rejects a
  chunk/document/source that points at another tenant's parent.
* Deleting a document or source cascades to its chunks (vectors) and jobs in the same
  transaction; the original object in storage is removed through the ``storage_deletions``
  outbox so a crash can never leave an unreferenced file behind forever.
* ``app.list_stuck_jobs`` / ``app.list_pending_storage_deletions`` are the only cross-tenant read
  paths (SECURITY DEFINER, minimal columns). They let the maintenance sweeper find work without
  a BYPASSRLS role; it then re-enters each tenant's own context to act.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.core.rls import enable_tenant_rls_statements

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_app"
TABLES = (
    "knowledge_sources",
    "documents",
    "document_chunks",
    "ingestion_jobs",
    "storage_deletions",
)


def _run(*statements: str) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    _run(
        """
        CREATE TABLE knowledge_sources (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          chatbot_id uuid NOT NULL,
          kind text NOT NULL,
          name text NOT NULL,
          status text NOT NULL DEFAULT 'pending',
          config jsonb NOT NULL DEFAULT '{}'::jsonb,
          stats jsonb NOT NULL DEFAULT '{}'::jsonb,
          last_synced_at timestamptz,
          created_by uuid REFERENCES users (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_knowledge_sources_org_id_id UNIQUE (org_id, id),
          CONSTRAINT fk_knowledge_sources_chatbot FOREIGN KEY (org_id, chatbot_id)
            REFERENCES chatbots (org_id, id) ON DELETE CASCADE,
          CONSTRAINT ck_knowledge_sources_kind CHECK (kind IN ('file', 'website')),
          CONSTRAINT ck_knowledge_sources_status
            CHECK (status IN ('pending', 'syncing', 'ready', 'partial', 'failed')),
          CONSTRAINT ck_knowledge_sources_name_length CHECK (char_length(name) BETWEEN 1 AND 200)
        )
        """,
        "CREATE INDEX ix_knowledge_sources_chatbot ON knowledge_sources (org_id, chatbot_id)",
        # One implicit "Uploaded files" source per chatbot.
        "CREATE UNIQUE INDEX uq_knowledge_sources_chatbot_file ON knowledge_sources (chatbot_id) "
        "WHERE kind = 'file'",
        """
        CREATE TABLE documents (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          chatbot_id uuid NOT NULL,
          source_id uuid NOT NULL,
          title text NOT NULL,
          uri text NOT NULL,
          storage_key text,
          mime_type text,
          size_bytes bigint NOT NULL DEFAULT 0,
          file_hash bytea,
          content_hash bytea,
          http_etag text,
          version integer NOT NULL DEFAULT 0,
          status text NOT NULL DEFAULT 'queued',
          error_code text,
          error_message text,
          page_count integer,
          token_count integer,
          chunk_count integer NOT NULL DEFAULT 0,
          embedding_model text,
          created_by uuid REFERENCES users (id) ON DELETE SET NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_documents_org_id_id UNIQUE (org_id, id),
          CONSTRAINT fk_documents_source FOREIGN KEY (org_id, source_id)
            REFERENCES knowledge_sources (org_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_documents_chatbot FOREIGN KEY (org_id, chatbot_id)
            REFERENCES chatbots (org_id, id) ON DELETE CASCADE,
          CONSTRAINT ck_documents_status
            CHECK (status IN ('queued', 'processing', 'ready', 'failed')),
          CONSTRAINT ck_documents_title_length CHECK (char_length(title) BETWEEN 1 AND 300),
          CONSTRAINT ck_documents_size CHECK (size_bytes >= 0),
          CONSTRAINT uq_documents_source_uri UNIQUE (source_id, uri)
        )
        """,
        "CREATE INDEX ix_documents_chatbot_status ON documents (org_id, chatbot_id, status)",
        "CREATE INDEX ix_documents_source ON documents (source_id)",
        # Identical uploads to one chatbot are rejected by the database, not just the app (races).
        "CREATE UNIQUE INDEX uq_documents_chatbot_file_hash ON documents (chatbot_id, file_hash) "
        "WHERE file_hash IS NOT NULL",
        """
        CREATE TABLE document_chunks (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          chatbot_id uuid NOT NULL,
          document_id uuid NOT NULL,
          document_version integer NOT NULL,
          ordinal integer NOT NULL,
          content text NOT NULL,
          embedded_text text,
          token_count integer NOT NULL,
          heading_path text[] NOT NULL DEFAULT '{}',
          page_start integer,
          page_end integer,
          embedding vector(1536) NOT NULL,
          embedding_model text NOT NULL,
          fts tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT fk_document_chunks_document FOREIGN KEY (org_id, document_id)
            REFERENCES documents (org_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_document_chunks_chatbot FOREIGN KEY (org_id, chatbot_id)
            REFERENCES chatbots (org_id, id) ON DELETE CASCADE,
          CONSTRAINT uq_document_chunks_version_ordinal
            UNIQUE (document_id, document_version, ordinal),
          CONSTRAINT ck_document_chunks_ordinal CHECK (ordinal >= 0)
        )
        """,
        "CREATE INDEX ix_document_chunks_chatbot ON document_chunks (org_id, chatbot_id)",
        "CREATE INDEX ix_document_chunks_fts ON document_chunks USING gin (fts)",
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
        """
        CREATE TABLE ingestion_jobs (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL,
          chatbot_id uuid NOT NULL,
          source_id uuid NOT NULL,
          document_id uuid,
          kind text NOT NULL,
          status text NOT NULL DEFAULT 'queued',
          stage text,
          attempt integer NOT NULL DEFAULT 0,
          max_attempts integer NOT NULL DEFAULT 4,
          celery_task_id text,
          queued_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz,
          finished_at timestamptz,
          heartbeat_at timestamptz,
          error_code text,
          error_detail text,
          stats jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by uuid REFERENCES users (id) ON DELETE SET NULL,
          CONSTRAINT fk_ingestion_jobs_source FOREIGN KEY (org_id, source_id)
            REFERENCES knowledge_sources (org_id, id) ON DELETE CASCADE,
          CONSTRAINT fk_ingestion_jobs_document FOREIGN KEY (org_id, document_id)
            REFERENCES documents (org_id, id) ON DELETE CASCADE,
          CONSTRAINT ck_ingestion_jobs_kind CHECK (kind IN ('process_document', 'crawl')),
          CONSTRAINT ck_ingestion_jobs_status
            CHECK (status IN ('queued', 'processing', 'succeeded', 'failed')),
          CONSTRAINT ck_ingestion_jobs_doc_required
            CHECK (kind <> 'process_document' OR document_id IS NOT NULL)
        )
        """,
        "CREATE INDEX ix_ingestion_jobs_status_queued ON ingestion_jobs (status, queued_at)",
        "CREATE INDEX ix_ingestion_jobs_source ON ingestion_jobs (org_id, source_id)",
        # At most one active job per document / per crawl source: no duplicate processing.
        "CREATE UNIQUE INDEX uq_ingestion_jobs_active_document ON ingestion_jobs (document_id) "
        "WHERE document_id IS NOT NULL AND status IN ('queued', 'processing')",
        "CREATE UNIQUE INDEX uq_ingestion_jobs_active_crawl ON ingestion_jobs (source_id) "
        "WHERE kind = 'crawl' AND status IN ('queued', 'processing')",
        """
        CREATE TABLE storage_deletions (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
          storage_key text NOT NULL,
          attempts integer NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    )
    for table in ("knowledge_sources", "documents"):
        _run(
            f"CREATE TRIGGER trg_{table}_touch BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
        )
    for table in TABLES:
        _run(*enable_tenant_rls_statements(table))

    # --- narrow cross-tenant read paths for the maintenance sweeper -----------------------
    for table in ("ingestion_jobs", "storage_deletions"):
        _run(
            f"""
            DO $$
            BEGIN
              EXECUTE format(
                'CREATE POLICY owner_read ON {table} FOR SELECT TO %I USING (true)',
                current_user
              );
            END
            $$
            """
        )
    _run(
        """
        CREATE FUNCTION app.list_stuck_jobs(p_stuck_before timestamptz, p_queued_before timestamptz)
        RETURNS TABLE (job_id uuid, org_id uuid, kind text, status text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT j.id, j.org_id, j.kind, j.status
          FROM public.ingestion_jobs j
          WHERE (j.status = 'processing'
                 AND coalesce(j.heartbeat_at, j.started_at) < p_stuck_before)
             OR (j.status = 'queued' AND j.queued_at < p_queued_before)
          ORDER BY j.queued_at
          LIMIT 200
        $$
        """,
        """
        CREATE FUNCTION app.list_pending_storage_deletions(p_limit integer)
        RETURNS TABLE (deletion_id uuid, org_id uuid, storage_key text)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT d.id, d.org_id, d.storage_key
          FROM public.storage_deletions d
          ORDER BY d.created_at
          LIMIT least(p_limit, 500)
        $$
        """,
        "REVOKE ALL ON FUNCTION app.list_stuck_jobs(timestamptz, timestamptz) FROM PUBLIC",
        "REVOKE ALL ON FUNCTION app.list_pending_storage_deletions(integer) FROM PUBLIC",
    )

    tables = ", ".join(TABLES)
    _run(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {APP_ROLE};
            GRANT EXECUTE ON FUNCTION app.list_stuck_jobs(timestamptz, timestamptz)
              TO {APP_ROLE};
            GRANT EXECUTE ON FUNCTION app.list_pending_storage_deletions(integer) TO {APP_ROLE};
          END IF;
        END
        $$
        """  # noqa: S608  # constant identifiers, no user input
    )


def downgrade() -> None:
    _run(
        "DROP FUNCTION IF EXISTS app.list_pending_storage_deletions(integer)",
        "DROP FUNCTION IF EXISTS app.list_stuck_jobs(timestamptz, timestamptz)",
        "DROP TABLE IF EXISTS storage_deletions",
        "DROP TABLE IF EXISTS ingestion_jobs",
        "DROP TABLE IF EXISTS document_chunks",
        "DROP TABLE IF EXISTS documents",
        "DROP TABLE IF EXISTS knowledge_sources",
    )
