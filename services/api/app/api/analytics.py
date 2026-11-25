"""Organization analytics from persisted conversation events and usage rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DbDep, require
from app.services import analytics as service
from app.services.tenancy.context import TenantContext


def no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/orgs/{org_id}", tags=["analytics"], dependencies=[Depends(no_cache)])
AnalyticsRead = Annotated[TenantContext, Depends(require("analytics:read"))]
Metric = Literal["conversations", "resolved", "tokens", "cost"]
Interval = Literal["day", "month"]


@router.get("/analytics/summary")
async def summary(
    org_id: uuid.UUID,
    ctx: AnalyticsRead,
    db: DbDep,
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    return await service.compute_summary(
        db,
        ctx.org.id,
        from_at=from_at,
        to_at=to_at,
        chatbot_id=chatbot_id,
        channel=channel,
    )


@router.get("/analytics/timeseries")
async def timeseries(
    org_id: uuid.UUID,
    ctx: AnalyticsRead,
    db: DbDep,
    metric: Metric = "conversations",
    interval: Interval = "day",
    chatbot_id: uuid.UUID | None = None,
    channel: str | None = None,
    from_at: Annotated[datetime | None, Query(alias="from")] = None,
    to_at: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    return await service.timeseries(
        db,
        ctx.org.id,
        metric=metric,
        interval=interval,
        from_at=from_at,
        to_at=to_at,
        chatbot_id=chatbot_id,
        channel=channel,
    )
