"""Liveness and readiness probes (unversioned, outside /api/v1)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ReadinessDep, SettingsDep
from app.schemas.health import LivenessResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def liveness(settings: SettingsDep) -> LivenessResponse:
    """The process is up and serving requests. Checks no dependencies."""
    return LivenessResponse(service=settings.app_name, version=settings.app_version)


@router.get(
    "/readyz",
    summary="Readiness probe",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(
    response: Response, settings: SettingsDep, service: ReadinessDep
) -> ReadinessResponse:
    """Postgres (with pgvector and migrations at head) and Redis are reachable."""
    checks = await service.run()
    healthy = all(check.status == "ok" for check in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    response.headers["Cache-Control"] = "no-store"
    return ReadinessResponse(
        status="ok" if healthy else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        checks=checks,
    )
