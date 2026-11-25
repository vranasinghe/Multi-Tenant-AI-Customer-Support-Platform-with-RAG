"""Row-Level Security and constraint tests against a real, migrated Postgres.

docs/DATABASE.md §4.4: as the runtime role without GUCs every tenant table is empty; with a GUC
only that tenant's rows are visible and writes for another tenant are rejected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

pytestmark = pytest.mark.integration

TENANT_TABLES = ("organizations", "memberships", "invitations", "audit_logs")


@dataclass(frozen=True)
class Seed:
    org_a: uuid.UUID
    org_b: uuid.UUID
    user_a: uuid.UUID
    user_b: uuid.UUID
    invite_hash_b: bytes


def _scoped(
    conn: Connection, *, org: uuid.UUID | None = None, user: uuid.UUID | None = None
) -> None:
    if org is not None:
        conn.execute(text("SELECT set_config('app.current_org_id', :v, true)"), {"v": str(org)})
    if user is not None:
        conn.execute(text("SELECT set_config('app.current_user_id', :v, true)"), {"v": str(user)})


@pytest.fixture
def seed(owner_engine: Engine) -> Seed:
    s = Seed(
        org_a=uuid.uuid4(),
        org_b=uuid.uuid4(),
        user_a=uuid.uuid4(),
        user_b=uuid.uuid4(),
        invite_hash_b=uuid.uuid4().bytes * 2,
    )
    expires = datetime.now(UTC) + timedelta(days=7)
    with owner_engine.begin() as c:
        for uid, mail in ((s.user_a, "a"), (s.user_b, "b")):
            c.execute(
                text("INSERT INTO users (id, email, name) VALUES (:id, :e, :n)"),
                {"id": uid, "e": f"{mail}-{uid}@example.com", "n": f"User {mail}"},
            )
        for oid, owner, slug in ((s.org_a, s.user_a, "a"), (s.org_b, s.user_b, "b")):
            c.execute(
                text(
                    "INSERT INTO organizations (id, name, slug, created_by) "
                    "VALUES (:id, :n, :s, :u)"
                ),
                {"id": oid, "n": f"Org {slug}", "s": f"{slug}-{oid}", "u": owner},
            )
            c.execute(
                text(
                    "INSERT INTO memberships (id, org_id, user_id, role) "
                    "VALUES (:id, :o, :u, 'owner')"
                ),
                {"id": uuid.uuid4(), "o": oid, "u": owner},
            )
            c.execute(
                text(
                    "INSERT INTO invitations "
                    "(id, org_id, email, role, token_hash, invited_by, expires_at) "
                    "VALUES (:id, :o, :e, 'agent', :h, :u, :x)"
                ),
                {
                    "id": uuid.uuid4(),
                    "o": oid,
                    "e": f"invitee-{oid}@example.com",
                    "h": s.invite_hash_b if oid == s.org_b else uuid.uuid4().bytes * 2,
                    "u": owner,
                    "x": expires,
                },
            )
            c.execute(
                text(
                    "INSERT INTO audit_logs (id, org_id, actor_type, actor_id, action) "
                    "VALUES (:id, :o, 'user', :u, 'org.created')"
                ),
                {"id": uuid.uuid4(), "o": oid, "u": owner},
            )
    return s


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_runtime_role_without_context_sees_no_rows(
    app_engine: Engine, seed: Seed, table: str
) -> None:
    with app_engine.begin() as conn:
        assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0  # noqa: S608  # constant identifiers, no user input


@pytest.mark.parametrize("table", ["memberships", "invitations", "audit_logs"])
def test_org_context_exposes_only_that_orgs_rows(
    app_engine: Engine, seed: Seed, table: str
) -> None:
    with app_engine.begin() as conn:
        _scoped(conn, org=seed.org_a)
        org_ids = set(conn.scalars(text(f"SELECT org_id FROM {table}")))  # noqa: S608  # constant identifiers, no user input

    assert org_ids == {seed.org_a}


def test_organizations_visible_through_org_context_or_own_membership(
    app_engine: Engine, seed: Seed
) -> None:
    with app_engine.begin() as conn:
        _scoped(conn, org=seed.org_a)
        assert set(conn.scalars(text("SELECT id FROM organizations"))) == {seed.org_a}
    with app_engine.begin() as conn:
        _scoped(conn, user=seed.user_b)  # org switcher: user context only
        assert set(conn.scalars(text("SELECT id FROM organizations"))) == {seed.org_b}


def test_user_context_alone_lists_only_own_memberships(app_engine: Engine, seed: Seed) -> None:
    with app_engine.begin() as conn:
        _scoped(conn, user=seed.user_a)
        rows = set(conn.scalars(text("SELECT user_id FROM memberships")))

    assert rows == {seed.user_a}


def _run_as_app(
    engine: Engine,
    sql: str,
    params: dict[str, object] | None = None,
    *,
    org: uuid.UUID | None = None,
    user: uuid.UUID | None = None,
) -> None:
    with engine.begin() as conn:
        _scoped(conn, org=org, user=user)
        conn.execute(text(sql), params or {})


def test_cannot_insert_invitation_for_another_org(app_engine: Engine, seed: Seed) -> None:
    with pytest.raises(ProgrammingError, match="row-level security"):
        _run_as_app(
            app_engine,
            "INSERT INTO invitations (id, org_id, email, role, token_hash, expires_at) "
            "VALUES (:id, :o, 'x@example.com', 'viewer', :h, now() + interval '1 day')",
            {"id": uuid.uuid4(), "o": seed.org_b, "h": uuid.uuid4().bytes * 2},
            org=seed.org_a,
        )


def test_cannot_insert_membership_for_someone_else(app_engine: Engine, seed: Seed) -> None:
    """Self-join only: nobody can be added to an org on their behalf at the SQL level."""
    with pytest.raises(ProgrammingError, match="row-level security"):
        _run_as_app(
            app_engine,
            "INSERT INTO memberships (id, org_id, user_id, role) VALUES (:id, :o, :u, 'owner')",
            {"id": uuid.uuid4(), "o": seed.org_a, "u": seed.user_b},
            org=seed.org_a,
            user=seed.user_a,
        )


def test_cannot_update_or_delete_other_orgs_membership(app_engine: Engine, seed: Seed) -> None:
    with app_engine.begin() as conn:
        _scoped(conn, org=seed.org_a, user=seed.user_a)
        updated = conn.execute(
            text("UPDATE memberships SET role = 'viewer' WHERE org_id = :o"), {"o": seed.org_b}
        ).rowcount
        deleted = conn.execute(
            text("DELETE FROM memberships WHERE org_id = :o"), {"o": seed.org_b}
        ).rowcount

    assert (updated, deleted) == (0, 0)


def test_audit_logs_are_append_only_for_runtime_role(app_engine: Engine, seed: Seed) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        _run_as_app(app_engine, "UPDATE audit_logs SET action = 'tampered'", org=seed.org_a)
    with pytest.raises(ProgrammingError, match="permission denied"):
        _run_as_app(app_engine, "DELETE FROM audit_logs", org=seed.org_a)
    with app_engine.begin() as conn:  # inserting is allowed
        _scoped(conn, org=seed.org_a)
        conn.execute(
            text(
                "INSERT INTO audit_logs (id, org_id, actor_type, action) "
                "VALUES (:id, :o, 'system', 'org.updated')"
            ),
            {"id": uuid.uuid4(), "o": seed.org_a},
        )


def test_resolve_invitation_works_without_tenant_context(app_engine: Engine, seed: Seed) -> None:
    with app_engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM invitations")) == 0  # RLS hides rows
        row = conn.execute(
            text("SELECT org_id, role FROM app.resolve_invitation(:h)"), {"h": seed.invite_hash_b}
        ).one()
        missing = conn.execute(
            text("SELECT * FROM app.resolve_invitation(:h)"), {"h": b"\x00" * 32}
        ).all()

    assert (row.org_id, row.role) == (seed.org_b, "agent")
    assert missing == []


def test_roles_are_constrained_to_known_values(owner_engine: Engine, seed: Seed) -> None:
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO memberships (id, org_id, user_id, role) "
                "VALUES (:id, :o, :u, 'editor')"  # legacy name from earlier docs
            ),
            {"id": uuid.uuid4(), "o": seed.org_a, "u": seed.user_b},
        )


def test_invitation_cannot_target_owner_role(owner_engine: Engine, seed: Seed) -> None:
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO invitations (id, org_id, email, role, token_hash, expires_at) "
                "VALUES (:id, :o, 'o@example.com', 'owner', :h, now() + interval '1 day')"
            ),
            {"id": uuid.uuid4(), "o": seed.org_a, "h": uuid.uuid4().bytes * 2},
        )


def test_only_one_pending_invitation_per_email(owner_engine: Engine, seed: Seed) -> None:
    params = {"o": seed.org_a, "e": "dup@example.com"}
    sql = text(
        "INSERT INTO invitations (id, org_id, email, role, token_hash, expires_at) "
        "VALUES (:id, :o, :e, 'viewer', :h, now() + interval '1 day')"
    )
    with owner_engine.begin() as conn:
        conn.execute(sql, {**params, "id": uuid.uuid4(), "h": uuid.uuid4().bytes * 2})
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        conn.execute(sql, {**params, "id": uuid.uuid4(), "h": uuid.uuid4().bytes * 2})


def test_email_is_case_insensitive_unique(owner_engine: Engine, seed: Seed) -> None:
    with pytest.raises(IntegrityError), owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email, name) VALUES (:id, :e, 'Dup')"),
            {"id": uuid.uuid4(), "e": f"A-{seed.user_a}@EXAMPLE.com"},
        )


def test_last_owner_cannot_be_removed_or_demoted_at_database_level(
    owner_engine: Engine, seed: Seed
) -> None:
    with pytest.raises(DBAPIError, match="last_owner"), owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM memberships WHERE org_id = :o"), {"o": seed.org_a})
    with pytest.raises(DBAPIError, match="last_owner"), owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE memberships SET role = 'admin' WHERE org_id = :o"), {"o": seed.org_a}
        )


def test_owner_can_be_demoted_when_another_owner_exists(owner_engine: Engine, seed: Seed) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO memberships (id, org_id, user_id, role) VALUES (:id, :o, :u, 'owner')"
            ),
            {"id": uuid.uuid4(), "o": seed.org_a, "u": seed.user_b},
        )
        conn.execute(
            text("UPDATE memberships SET role = 'admin' WHERE org_id = :o AND user_id = :u"),
            {"o": seed.org_a, "u": seed.user_a},
        )


def test_membership_identity_columns_are_immutable(owner_engine: Engine, seed: Seed) -> None:
    with pytest.raises(DBAPIError, match="immutable"), owner_engine.begin() as conn:
        conn.execute(
            text("UPDATE memberships SET user_id = :u WHERE org_id = :o"),
            {"o": seed.org_a, "u": seed.user_b},
        )
