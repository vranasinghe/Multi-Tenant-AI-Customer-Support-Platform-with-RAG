"""MIG-01 diagnostic pytest plugin: data state before the migration round-trip and its error.

Read-only against the disposable test database. Records counts, constraint definitions and the
tail of Alembic's stderr; no message content.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

QUERIES = {
    "revision": "SELECT version_num FROM alembic_version",
    "organizations": "SELECT count(*) FROM organizations",
    "conversations": "SELECT count(*) FROM conversations",
    "messages": "SELECT count(*) FROM messages",
    "chat_usage": "SELECT count(*) FROM chat_usage",
    "chat_usage_without_conversation": (
        "SELECT count(*) FROM chat_usage u WHERE NOT EXISTS (SELECT 1 FROM conversations c "
        "WHERE c.org_id = u.org_id AND c.id = u.conversation_id)"
    ),
    "orgs_with_orphan_usage": (
        "SELECT count(DISTINCT u.org_id) FROM chat_usage u WHERE NOT EXISTS (SELECT 1 FROM "
        "conversations c WHERE c.org_id = u.org_id AND c.id = u.conversation_id)"
    ),
}
CONSTRAINTS = (
    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conrelid = 'chat_usage'::regclass ORDER BY conname"
)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    if item.name != "test_chat_migration_roundtrip":
        return (yield)
    report: dict = {"state_before_downgrade": {}}
    engine = create_engine(item.funcargs["test_database"].owner_url)
    with engine.connect() as conn:
        for name, query in QUERIES.items():
            report["state_before_downgrade"][name] = conn.execute(text(query)).scalar()
        report["chat_usage_constraints"] = [list(r) for r in conn.execute(text(CONSTRAINTS))]
    engine.dispose()
    original = subprocess.run

    def run(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except subprocess.CalledProcessError as exc:
            lines = exc.stderr.decode(errors="replace").splitlines()
            wanted = re.compile(r"psycopg\.errors|sqlalchemy\.exc|^DETAIL|Running downgrade")
            report["alembic_error"] = [line[:300] for line in lines if wanted.search(line)]
            raise

    subprocess.run = run
    try:
        return (yield)
    finally:
        subprocess.run = original
        folder = Path(os.environ.get("AUDIT_OUTPUT_DIR", "/tmp/mig-probe"))
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mig-state.json").write_text(json.dumps(report, indent=2, default=str))
