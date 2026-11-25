from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine

from tests.support.database import TestDatabase


@pytest.fixture(scope="session")
def owner_engine(test_database: TestDatabase) -> Iterator[Engine]:
    engine = create_engine(test_database.owner_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(test_database: TestDatabase) -> Iterator[Engine]:
    """Connects as the unprivileged runtime role (RLS enforced)."""
    engine = create_engine(test_database.app_url)
    yield engine
    engine.dispose()
