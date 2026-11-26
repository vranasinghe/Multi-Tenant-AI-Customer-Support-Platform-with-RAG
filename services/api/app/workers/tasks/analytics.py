"""Daily analytics rollup and conversation retention. Logic lives in services."""

from __future__ import annotations

from app.core.logging import get_logger
from app.rag.runtime import get_runtime
from app.services.retention import list_orgs_sync, purge_org_sync, snapshot_org_sync
from app.workers.celery_app import celery_app

log = get_logger(__name__)


@celery_app.task(name="analytics.retention")
def retention() -> dict[str, int]:
    rt = get_runtime()
    with rt.session_factory() as session, session.begin():
        orgs = list_orgs_sync(session)
    purged = 0
    for org_id, days in orgs:
        with rt.tenant_tx(org_id) as session:
            purged += purge_org_sync(session, org_id, days)
    log.info("analytics.retention", organizations=len(orgs), conversations=purged)
    return {"organizations": len(orgs), "conversations": purged}


@celery_app.task(name="analytics.rollup")
def rollup() -> dict[str, int]:
    """Rebuild per-tenant daily snapshots from live source tables."""
    rt = get_runtime()
    with rt.session_factory() as session, session.begin():
        orgs = list_orgs_sync(session)
    updated = 0
    for org_id, _days in orgs:
        with rt.tenant_tx(org_id) as session:
            updated += snapshot_org_sync(session)
    log.info("analytics.rollup", organizations=len(orgs))
    return {"organizations": len(orgs), "updated": updated}
