"""Row-Level Security helpers shared by migrations, the CLI and tests (docs/DATABASE.md §4, §7).

``enable_tenant_rls`` is the one way a migration should protect a table with an ``org_id`` column,
so the policy is never forgotten. ``find_unprotected_tables`` powers ``python -m app.cli
check-rls``, which CI runs to fail any tenant table without ``FORCE`` RLS and a policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Connection

#: Tenant tables whose tenant key is not an ``org_id`` column.
TENANT_ROOT_TABLES = frozenset({"organizations"})


def enable_tenant_rls_statements(table: str, *, org_column: str = "org_id") -> list[str]:
    """SQL that enables + forces RLS and installs the standard ``tenant_isolation`` policy."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({org_column} = app.current_org_id()) "
        f"WITH CHECK ({org_column} = app.current_org_id())",
    ]


def enable_force_rls_statements(table: str) -> list[str]:
    """Enable + force RLS without adding a policy (for tables with bespoke per-command policies)."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
    ]


_UNPROTECTED_SQL = text(
    """
    SELECT c.relname AS table_name,
           c.relrowsecurity AS rls_enabled,
           c.relforcerowsecurity AS rls_forced,
           (SELECT count(*) FROM pg_policies p
             WHERE p.schemaname = n.nspname AND p.tablename = c.relname) AS policies
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND (
        c.relname = ANY(:roots)
        OR EXISTS (
          SELECT 1 FROM pg_attribute a
          WHERE a.attrelid = c.oid AND a.attname = 'org_id' AND NOT a.attisdropped
        )
      )
    ORDER BY c.relname
    """
)


def find_unprotected_tables(conn: Connection) -> list[str]:
    """Names of tenant tables lacking enabled+forced RLS or any policy."""
    rows = conn.execute(_UNPROTECTED_SQL, {"roots": sorted(TENANT_ROOT_TABLES)})
    return [
        row.table_name
        for row in rows
        if not (row.rls_enabled and row.rls_forced and row.policies > 0)
    ]
