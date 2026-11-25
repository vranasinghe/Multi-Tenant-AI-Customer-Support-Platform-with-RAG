"""Identity and tenancy: users, sessions, email tokens, organizations, memberships, invitations,
audit log, Row-Level Security policies and integrity triggers.

Security design (docs/DATABASE.md §3-4, docs/SECURITY.md §4-5):

* Global tables (users, sessions, email_tokens) hold credentials/hashes only; no tenant data.
* Tenant tables are protected with ENABLE + FORCE RLS. Policies read transaction-local GUCs
  (`app.current_org_id`, `app.current_user_id`) that only the API sets after server-side
  verification of the session and membership.
* `memberships` INSERT is limited to self-join (user_id = current user): no SQL path can add
  somebody else to an organization. `audit_logs` is append-only for the runtime role.
* DB-level safety nets: last-owner trigger, immutable membership identity, CHECK constraints on
  roles (owner is never invitable), partial unique indexes for pending invitations.
* `app.resolve_invitation(token_hash)` is the narrow SECURITY DEFINER read path used before a
  tenant context exists. Because tables are FORCEd, definer functions run as the table owner, so
  the owner role gets explicit read-only policies (the runtime role is a different role).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.core.rls import enable_force_rls_statements, enable_tenant_rls_statements

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "platform_app"
TABLES = (
    "users",
    "sessions",
    "email_tokens",
    "organizations",
    "memberships",
    "invitations",
    "audit_logs",
)


def _run(*statements: str) -> None:
    for statement in statements:
        op.execute(statement)


def upgrade() -> None:
    # ----------------------------------------------------------------- helpers
    _run(
        """
        CREATE FUNCTION app.touch_updated_at() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END
        $$
        """
    )

    # ------------------------------------------------------------ identity (global)
    _run(
        """
        CREATE TABLE users (
          id uuid PRIMARY KEY,
          email citext NOT NULL,
          email_verified_at timestamptz,
          password_hash text,
          name text NOT NULL,
          locale text NOT NULL DEFAULT 'en',
          status text NOT NULL DEFAULT 'active',
          last_login_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_users_email UNIQUE (email),
          CONSTRAINT ck_users_name_length CHECK (char_length(name) BETWEEN 1 AND 120),
          CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled'))
        )
        """,
        """
        CREATE TABLE sessions (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
          token_hash bytea NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          user_agent text,
          ip_prefix inet,
          CONSTRAINT uq_sessions_token_hash UNIQUE (token_hash)
        )
        """,
        "CREATE INDEX ix_sessions_user_id ON sessions (user_id) WHERE revoked_at IS NULL",
        """
        CREATE TABLE email_tokens (
          id uuid PRIMARY KEY,
          user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
          purpose text NOT NULL,
          token_hash bytea NOT NULL,
          new_email citext,
          expires_at timestamptz NOT NULL,
          consumed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_email_tokens_token_hash UNIQUE (token_hash),
          CONSTRAINT ck_email_tokens_purpose
            CHECK (purpose IN ('verify_email', 'reset_password', 'change_email'))
        )
        """,
        "CREATE INDEX ix_email_tokens_user_purpose ON email_tokens (user_id, purpose)",
    )

    # --------------------------------------------------------------- tenancy
    _run(
        """
        CREATE TABLE organizations (
          id uuid PRIMARY KEY,
          name text NOT NULL,
          slug citext NOT NULL,
          status text NOT NULL DEFAULT 'active',
          settings jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by uuid REFERENCES users (id) ON DELETE SET NULL,
          deletion_requested_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          deleted_at timestamptz,
          CONSTRAINT uq_organizations_slug UNIQUE (slug),
          CONSTRAINT ck_organizations_name_length CHECK (char_length(name) BETWEEN 1 AND 120),
          CONSTRAINT ck_organizations_status
            CHECK (status IN ('active', 'restricted', 'suspended', 'pending_deletion'))
        )
        """,
        """
        CREATE TABLE memberships (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
          user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
          role text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_memberships_org_user UNIQUE (org_id, user_id),
          CONSTRAINT ck_memberships_role CHECK (role IN ('owner', 'admin', 'agent', 'viewer'))
        )
        """,
        "CREATE INDEX ix_memberships_user_id ON memberships (user_id)",
        """
        CREATE TABLE invitations (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
          email citext NOT NULL,
          role text NOT NULL,
          token_hash bytea NOT NULL,
          invited_by uuid REFERENCES users (id) ON DELETE SET NULL,
          expires_at timestamptz NOT NULL,
          accepted_at timestamptz,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT uq_invitations_token_hash UNIQUE (token_hash),
          CONSTRAINT ck_invitations_role CHECK (role IN ('admin', 'agent', 'viewer'))
        )
        """,
        """
        CREATE UNIQUE INDEX uq_invitations_org_email_pending ON invitations (org_id, email)
          WHERE accepted_at IS NULL AND revoked_at IS NULL
        """,
        """
        CREATE TABLE audit_logs (
          id uuid PRIMARY KEY,
          org_id uuid NOT NULL REFERENCES organizations (id),
          actor_type text NOT NULL,
          actor_id uuid,
          action text NOT NULL,
          target_type text,
          target_id uuid,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          ip_prefix inet,
          request_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_audit_logs_actor_type
            CHECK (actor_type IN ('user', 'system', 'api_key', 'platform_staff'))
        )
        """,
        "CREATE INDEX ix_audit_logs_org_created ON audit_logs (org_id, created_at DESC)",
    )

    # ----------------------------------------------------- updated_at maintenance
    for table in ("users", "organizations", "memberships"):
        _run(
            f"CREATE TRIGGER trg_{table}_touch BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
        )

    # ------------------------------------------------------ integrity safety nets
    _run(
        """
        CREATE FUNCTION app.enforce_membership_integrity() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP = 'UPDATE' AND (NEW.org_id <> OLD.org_id OR NEW.user_id <> OLD.user_id) THEN
            RAISE EXCEPTION 'membership identity columns are immutable' USING ERRCODE = 'LO002';
          END IF;
          IF OLD.role = 'owner' AND (TG_OP = 'DELETE' OR NEW.role <> 'owner')
             AND EXISTS (SELECT 1 FROM public.organizations o WHERE o.id = OLD.org_id)
             AND NOT EXISTS (
               SELECT 1 FROM public.memberships m
               WHERE m.org_id = OLD.org_id AND m.role = 'owner' AND m.id <> OLD.id
             )
          THEN
            RAISE EXCEPTION 'last_owner: an organization must keep at least one owner'
              USING ERRCODE = 'LO001';
          END IF;
          RETURN COALESCE(NEW, OLD);
        END
        $$
        """,
        "CREATE TRIGGER trg_memberships_integrity BEFORE UPDATE OR DELETE ON memberships "
        "FOR EACH ROW EXECUTE FUNCTION app.enforce_membership_integrity()",
    )

    # ---------------------------------------------------------------------- RLS
    _run(*enable_force_rls_statements("organizations"))
    _run(
        """
        CREATE POLICY org_select ON organizations FOR SELECT USING (
          id = app.current_org_id()
          OR EXISTS (
            SELECT 1 FROM memberships m
            WHERE m.org_id = organizations.id AND m.user_id = app.current_user_id()
          )
        )
        """,
        "CREATE POLICY org_insert ON organizations FOR INSERT "
        "WITH CHECK (id = app.current_org_id())",
        "CREATE POLICY org_update ON organizations FOR UPDATE "
        "USING (id = app.current_org_id()) WITH CHECK (id = app.current_org_id())",
    )

    _run(*enable_force_rls_statements("memberships"))
    _run(
        "CREATE POLICY membership_select ON memberships FOR SELECT "
        "USING (org_id = app.current_org_id() OR user_id = app.current_user_id())",
        # Self-join only: a membership is created by its own user (org creation / invitation
        # accept), never on someone else's behalf.
        "CREATE POLICY membership_insert ON memberships FOR INSERT "
        "WITH CHECK (org_id = app.current_org_id() AND user_id = app.current_user_id())",
        "CREATE POLICY membership_update ON memberships FOR UPDATE "
        "USING (org_id = app.current_org_id()) WITH CHECK (org_id = app.current_org_id())",
        "CREATE POLICY membership_delete ON memberships FOR DELETE "
        "USING (org_id = app.current_org_id())",
    )

    _run(*enable_tenant_rls_statements("invitations"))

    _run(*enable_force_rls_statements("audit_logs"))
    _run(
        "CREATE POLICY audit_select ON audit_logs FOR SELECT USING (org_id = app.current_org_id())",
        "CREATE POLICY audit_insert ON audit_logs FOR INSERT "
        "WITH CHECK (org_id = app.current_org_id())",
    )

    # Definer functions run as the (FORCEd) table owner; give that role read-only policies.
    for table in ("organizations", "memberships", "invitations"):
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

    # -------------------------------------------------------- pre-tenant resolver
    _run(
        """
        CREATE FUNCTION app.resolve_invitation(p_token_hash bytea)
        RETURNS TABLE (
          invitation_id uuid, org_id uuid, email citext, role text,
          expires_at timestamptz, accepted_at timestamptz, revoked_at timestamptz
        )
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public AS $$
          SELECT i.id, i.org_id, i.email, i.role, i.expires_at, i.accepted_at, i.revoked_at
          FROM public.invitations i
          WHERE i.token_hash = p_token_hash
        $$
        """,
        "REVOKE ALL ON FUNCTION app.resolve_invitation(bytea) FROM PUBLIC",
    )

    # ------------------------------------------------------------------ privileges
    tables = ", ".join(TABLES)
    _run(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {APP_ROLE};
            REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM {APP_ROLE};
            REVOKE DELETE ON organizations FROM {APP_ROLE};
            GRANT EXECUTE ON FUNCTION app.resolve_invitation(bytea) TO {APP_ROLE};
          END IF;
        END
        $$
        """  # noqa: S608  # constant identifiers, no user input
    )


def downgrade() -> None:
    _run(
        "DROP POLICY IF EXISTS org_select ON organizations",  # depends on memberships
        "DROP FUNCTION IF EXISTS app.resolve_invitation(bytea)",
        "DROP TABLE IF EXISTS audit_logs",
        "DROP TABLE IF EXISTS invitations",
        "DROP TABLE IF EXISTS memberships",
        "DROP TABLE IF EXISTS organizations",
        "DROP TABLE IF EXISTS email_tokens",
        "DROP TABLE IF EXISTS sessions",
        "DROP TABLE IF EXISTS users",
        "DROP FUNCTION IF EXISTS app.enforce_membership_integrity()",
        "DROP FUNCTION IF EXISTS app.touch_updated_at()",
    )
