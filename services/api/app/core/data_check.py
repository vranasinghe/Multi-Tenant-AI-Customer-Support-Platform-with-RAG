"""A fingerprint of everything a backup has to bring back (`python -m app.cli verify-data`).

Taken on the source and on the restored copy and compared. It holds counts, hashes, object keys
by record id and schema protections, never row contents. Run it as the schema owner, which sees
every tenant, with writers stopped on the source.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, text

from app.core.rls import find_unprotected_tables
from app.rag.storage import ObjectNotFoundError, ObjectStore, StorageError

_TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
_PROTECTIONS = {
    "row_security": "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
    "WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace ORDER BY relname",
    "policies": "SELECT tablename, policyname, cmd, roles::text, qual, with_check "
    "FROM pg_policies WHERE schemaname = 'public' ORDER BY tablename, policyname",
    "grants": "SELECT grantee, table_name, privilege_type "
    "FROM information_schema.role_table_grants WHERE table_schema = 'public' "
    "ORDER BY grantee, table_name, privilege_type",
    "functions": "SELECT p.proname, p.prosecdef, md5(pg_get_functiondef(p.oid)), p.proacl::text "
    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'app' "
    "ORDER BY p.proname, 3",
    "constraints": "SELECT conrelid::regclass::text, conname, convalidated, "
    "pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace = 'public'::regnamespace "
    "ORDER BY 1, 2",
    "indexes": "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
    "ORDER BY indexname",
}
#: Records that point at an object that must exist. Documents also record its size.
_REFERENCES = (
    "SELECT id, storage_key, size_bytes FROM documents "
    "WHERE storage_key IS NOT NULL "
    "UNION ALL SELECT id, storage_key, NULL FROM conversation_exports "
    "WHERE status = 'ready' AND expires_at > now() ORDER BY 1"
)
_MAX_OBJECT_BYTES = 256 * 1024 * 1024


def _rows(connection: Connection, statement: str) -> list[list[Any]]:
    return [list(row) for row in connection.execute(text(statement))]


def _objects(connection: Connection, store: ObjectStore) -> dict[str, Any]:
    problems = []
    references = connection.execute(text(_REFERENCES)).all()
    for record_id, key, size in references:
        try:
            data = store.get(key, max_bytes=_MAX_OBJECT_BYTES)
        except ObjectNotFoundError:
            problems.append({"id": str(record_id), "problem": "missing"})
        except StorageError:
            problems.append({"id": str(record_id), "problem": "unreadable"})
        else:
            if size is not None and size != len(data):
                problems.append({"id": str(record_id), "problem": "size differs"})
    return {"referenced": len(references), "problems": problems}


def fingerprint(connection: Connection, store: ObjectStore) -> dict[str, Any]:
    connection.execute(text("SET TIME ZONE 'UTC'"))  # timestamps print the same on any host
    tables = {}
    for (name,) in connection.execute(text(_TABLES)).all():
        quoted = '"' + name.replace('"', '""') + '"'
        # Order independent and constant in memory: a count and the sum of row hashes.
        count, digest = connection.execute(
            text(f"SELECT count(*), sum(hashtextextended(t::text, 0)) FROM {quoted} t")  # noqa: S608
        ).one()
        tables[name] = {"rows": count, "digest": str(digest or 0)}
    return {
        "revision": connection.scalar(text("SELECT version_num FROM alembic_version")),
        "tables": tables,
        "protections": {key: _rows(connection, sql) for key, sql in _PROTECTIONS.items()},
        "unprotected_tables": find_unprotected_tables(connection),
        "objects": _objects(connection, store),
    }
