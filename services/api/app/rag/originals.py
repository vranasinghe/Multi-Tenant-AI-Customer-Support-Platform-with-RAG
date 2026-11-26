"""Who owns a stored original that is fetched again (a crawled web page).

Such an original is written under a **new** key every time, never over an existing one. The write
happens outside any database transaction, so it is bracketed by the ``storage_deletions`` outbox:

* ``stage``   before writing, record the key as "delete this unless it gets published". The row's
  ``created_at`` is the earliest time it may be reclaimed: later than the writer can still run.
* ``adopt``   in the fenced transaction that publishes it, remove that record, point the document
  at the new key and queue the previous object for deletion.
* ``release`` a writer that has finished writing but did not publish makes the object reclaimable
  now. A writer that died cannot, and the object is reclaimed once its time has come.

The purge claims a record (``attempts``) before it touches the object, and a claimed key can no
longer be adopted, so a document never points at an object that is being deleted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.ids import new_id
from app.core.logging import get_logger
from app.models.knowledge import StorageDeletion
from app.rag.errors import TransientIngestionError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.models.knowledge import Document
    from app.rag.runtime import Runtime

log = get_logger(__name__)

#: Added to the longest crawl task before an unpublished object may be reclaimed.
GRACE_MARGIN_SECONDS = 300


def grace_seconds(settings: Settings) -> int:
    """No crawl task outlives its hard time limit, so nothing can still be writing after this."""
    return settings.crawl_hard_time_limit_seconds + GRACE_MARGIN_SECONDS


def stage(s: Session, org_id: uuid.UUID, key: str, *, grace_seconds: int) -> None:
    s.execute(
        text(
            "INSERT INTO storage_deletions (id, org_id, storage_key, created_at) "
            "VALUES (:id, :org, :key, now() + make_interval(secs => :grace))"
        ),
        {"id": new_id(), "org": org_id, "key": key, "grace": grace_seconds},
    )


def adopt(s: Session, document: Document, key: str, *, size: int, etag: str | None) -> None:
    """Make ``key`` the document's original. The caller holds the document and its job claim."""
    record = s.execute(
        text(
            "DELETE FROM storage_deletions WHERE storage_key = :key AND attempts = 0 RETURNING id"
        ),
        {"key": key},
    ).first()
    if record is None:
        raise TransientIngestionError("storage_error", "staged original was reclaimed")
    previous = document.storage_key
    if previous and previous != key:
        s.add(StorageDeletion(org_id=document.org_id, storage_key=previous))
    document.storage_key = key
    document.size_bytes = size
    document.http_etag = etag


def release(rt: Runtime, org_id: uuid.UUID, key: str) -> None:
    """Reclaim an unpublished object at the next purge. Does nothing once ``key`` is adopted."""
    try:
        with rt.tenant_tx(org_id) as s:
            s.execute(
                text(
                    "UPDATE storage_deletions SET created_at = now() "
                    "WHERE storage_key = :key AND attempts = 0"
                ),
                {"key": key},
            )
    except SQLAlchemyError:  # the record keeps its original time: reclaimed later, not never
        log.warning("storage.release_failed", exc_info=True)
