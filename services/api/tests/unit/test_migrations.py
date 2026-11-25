from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.services.readiness import ALEMBIC_INI, expected_migration_heads


def test_single_linear_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    heads = script.get_heads()

    assert len(heads) == 1, f"multiple Alembic heads: {heads} — merge them"
    assert expected_migration_heads() == frozenset(heads)


def test_every_revision_has_a_downgrade() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))

    for revision in script.walk_revisions():
        assert hasattr(revision.module, "downgrade"), revision.revision
