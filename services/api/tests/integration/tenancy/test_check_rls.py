"""AC0.3: a tenant table without RLS must fail the lint that CI runs."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from app.core.rls import enable_tenant_rls_statements, find_unprotected_tables

pytestmark = pytest.mark.integration


def test_all_shipped_tenant_tables_are_protected(owner_engine: Engine) -> None:
    with owner_engine.connect() as conn:
        assert find_unprotected_tables(conn) == []


def test_table_with_org_id_but_no_policy_is_reported(owner_engine: Engine) -> None:
    with owner_engine.begin() as conn:
        conn.execute(text("CREATE TABLE lint_probe (id uuid PRIMARY KEY, org_id uuid NOT NULL)"))
        try:
            assert find_unprotected_tables(conn) == ["lint_probe"]
            for statement in enable_tenant_rls_statements("lint_probe"):
                conn.execute(text(statement))
            assert find_unprotected_tables(conn) == []
        finally:
            conn.execute(text("DROP TABLE lint_probe"))


def test_rls_enabled_but_not_forced_is_reported(owner_engine: Engine) -> None:
    with owner_engine.begin() as conn:
        conn.execute(text("CREATE TABLE lint_probe2 (id uuid PRIMARY KEY, org_id uuid NOT NULL)"))
        try:
            conn.execute(text("ALTER TABLE lint_probe2 ENABLE ROW LEVEL SECURITY"))
            conn.execute(
                text("CREATE POLICY p ON lint_probe2 USING (org_id = app.current_org_id())")
            )
            assert find_unprotected_tables(conn) == ["lint_probe2"]
        finally:
            conn.execute(text("DROP TABLE lint_probe2"))
