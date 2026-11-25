"""Identifier generation: time-ordered UUIDv7 primary keys created in the application (ADR-006)."""

from __future__ import annotations

import uuid

from uuid_utils.compat import uuid7


def new_id() -> uuid.UUID:
    return uuid7()
