"""Health contracts. Mirrored in packages/shared-types until TS types are generated from OpenAPI."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["ok", "error"]
OverallStatus = Literal["ok", "degraded"]


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str


class DependencyCheck(BaseModel):
    status: CheckStatus
    latency_ms: float = Field(ge=0)
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: OverallStatus
    service: str
    version: str
    environment: str
    checks: dict[str, DependencyCheck]
