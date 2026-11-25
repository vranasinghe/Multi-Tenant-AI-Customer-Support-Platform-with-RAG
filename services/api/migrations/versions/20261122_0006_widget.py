"""Verified widget origins and scoped anonymous resumption."""

from alembic import op

from app.core.rls import enable_tenant_rls_statements

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute(
        """ALTER TABLE chatbots ADD COLUMN widget_retention_days integer NOT NULL DEFAULT 7 CHECK(widget_retention_days BETWEEN 0 AND 30)"""  # noqa: E501
    )
    op.execute(
        """ALTER TABLE widget_sessions ADD COLUMN public_origin text, ADD COLUMN resume_hash text UNIQUE, ADD COLUMN resume_expires_at timestamptz"""  # noqa: E501
    )
    op.execute("""CREATE TABLE chatbot_domains (
      id uuid PRIMARY KEY, org_id uuid NOT NULL, chatbot_id uuid NOT NULL,
      origin text NOT NULL, token text NOT NULL, verified_until timestamptz,
      UNIQUE(org_id,chatbot_id,origin),
      FOREIGN KEY(org_id,chatbot_id) REFERENCES chatbots(org_id,id) ON DELETE CASCADE)""")
    for sql in enable_tenant_rls_statements("chatbot_domains"):
        op.execute(sql)
    for table in ("chatbot_domains", "chatbots"):
        op.execute(
            f"""DO $$ BEGIN EXECUTE format('CREATE POLICY widget_owner_read ON {table} FOR SELECT TO %I USING (true)',current_user); END $$"""  # noqa: E501
        )
    op.execute("""CREATE FUNCTION app.resolve_widget(p_key text,p_origin text)
      RETURNS TABLE(org_id uuid,chatbot_id uuid) LANGUAGE sql STABLE SECURITY DEFINER
      SET search_path=pg_catalog,public AS $$
      SELECT b.org_id,b.id FROM public.chatbots b JOIN public.chatbot_domains d
        ON d.org_id=b.org_id AND d.chatbot_id=b.id
      WHERE b.public_key=p_key AND b.status='active' AND b.deleted_at IS NULL
        AND d.origin=p_origin AND d.verified_until > now() $$""")
    op.execute("REVOKE ALL ON FUNCTION app.resolve_widget(text,text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app.resolve_widget(text,text) TO platform_app")
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON chatbot_domains TO platform_app")


def downgrade() -> None:
    op.execute("DROP FUNCTION app.resolve_widget(text,text)")
    op.execute("DROP POLICY widget_owner_read ON chatbots")
    op.execute("DROP TABLE chatbot_domains")
    op.execute(
        """ALTER TABLE widget_sessions DROP COLUMN public_origin,DROP COLUMN resume_hash,DROP COLUMN resume_expires_at"""  # noqa: E501
    )
    op.execute("ALTER TABLE chatbots DROP COLUMN widget_retention_days")
