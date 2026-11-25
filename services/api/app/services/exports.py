"""Authorized conversation CSV export. Files never leave through a public URL."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, not_found
from app.core.ids import new_id
from app.core.request_meta import RequestMeta
from app.models.conversations import ConversationExport
from app.models.identity import utcnow
from app.rag.storage import ObjectStore, key_belongs_to_org
from app.services.inbox import list_conversations
from app.services.tenancy.audit import record_audit

EXPORT_TTL = timedelta(days=7)
EXPORT_PAGE = 100
EXPORT_MAX_ROWS = 10_000


def export_key(org_id: uuid.UUID, export_id: uuid.UUID) -> str:
    return f"orgs/{org_id}/exports/{export_id}.csv"


async def create_export(
    db: AsyncSession,
    store: ObjectStore,
    *,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    meta: RequestMeta,
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    status: str | None = None,
) -> ConversationExport:
    export_id = new_id()
    key = export_key(org_id, export_id)
    if not key_belongs_to_org(key, org_id):
        raise ApiError(500, "export_failed", "Export path was rejected")
    rows, written = await _collect(
        db,
        org_id,
        chatbot_id=chatbot_id,
        channel=channel,
        from_at=from_at,
        to_at=to_at,
        status=status,
    )
    store.put(key, rows, content_type="text/csv; charset=utf-8")
    record = ConversationExport(
        id=export_id,
        org_id=org_id,
        created_by=actor_id,
        status="ready",
        row_count=written,
        storage_key=key,
        expires_at=utcnow() + EXPORT_TTL,
    )
    db.add(record)
    await record_audit(
        db,
        org_id=org_id,
        actor_id=actor_id,
        action="conversation.exported",
        target_type="conversation_export",
        target_id=export_id,
        metadata={"row_count": written, "channel": channel},
        meta=meta,
    )
    await db.flush()
    return record


async def _collect(
    db: AsyncSession,
    org_id: uuid.UUID,
    **filters: Any,
) -> tuple[bytes, int]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "conversation_id",
            "chatbot_id",
            "chatbot_name",
            "channel",
            "status",
            "preview",
            "satisfaction_score",
            "handoff_status",
            "unanswered_count",
            "created_at",
            "last_message_at",
        ]
    )
    cursor: str | None = None
    written = 0
    while written < EXPORT_MAX_ROWS:
        page = await list_conversations(db, org_id, cursor=cursor, limit=EXPORT_PAGE, **filters)
        for item in page["data"]:
            writer.writerow(
                [
                    str(item["id"]),
                    str(item["chatbot_id"]),
                    item["chatbot_name"],
                    item["channel"],
                    item["status"],
                    item["preview"],
                    item["satisfaction_score"] if item["satisfaction_score"] is not None else "",
                    item["handoff_status"] or "",
                    item["unanswered_count"],
                    item["created_at"].isoformat(),
                    item["last_message_at"].isoformat(),
                ]
            )
            written += 1
            if written >= EXPORT_MAX_ROWS:
                break
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    return buffer.getvalue().encode("utf-8"), written


async def get_export(
    db: AsyncSession, org_id: uuid.UUID, export_id: uuid.UUID
) -> ConversationExport:
    row = await db.scalar(
        select(ConversationExport).where(
            ConversationExport.org_id == org_id, ConversationExport.id == export_id
        )
    )
    if row is None:
        raise not_found()
    return row


async def download_export(
    db: AsyncSession, store: ObjectStore, org_id: uuid.UUID, export_id: uuid.UUID
) -> bytes:
    row = await get_export(db, org_id, export_id)
    if row.status != "ready" or row.expires_at <= utcnow():
        raise not_found()
    if not key_belongs_to_org(row.storage_key, org_id):
        raise not_found()
    return store.get(row.storage_key, max_bytes=20 * 1024 * 1024)


def export_out(row: ConversationExport) -> dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "row_count": row.row_count,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "download_path": f"/orgs/{row.org_id}/exports/{row.id}/download",
    }
