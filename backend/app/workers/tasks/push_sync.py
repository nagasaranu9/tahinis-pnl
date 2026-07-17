"""
PushOperations labor sync tasks.

Two cadences, both landing in the same upsert:

- `push.incremental_sync_all_tenants` (daily) re-pulls a trailing window so
  retroactive punch edits — a manager fixing a missed clock-out three days
  later — correct the Labor line without a full backfill.
- `push.realtime_sync_all_tenants` (every 15 min) refreshes today only, which
  is what makes "labor cost so far today" live.

Historical backfill is a separate task because it walks ~66 chunked API calls
and must not share a retry budget with the fast paths.
"""
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="push.incremental_sync_all_tenants", queue="default")
def incremental_sync_all_tenants() -> dict:
    """Dispatch a trailing-window sync for every tenant with an active config."""
    return asyncio.run(_dispatch_all("incremental"))


@celery_app.task(name="push.realtime_sync_all_tenants", queue="default")
def realtime_sync_all_tenants() -> dict:
    """Dispatch a today-only sync for every tenant with an active config."""
    return asyncio.run(_dispatch_all("realtime"))


async def _dispatch_all(job_type: str) -> dict:
    from sqlalchemy import select

    from app.db.models.push_labor import PushSyncConfig
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        configs = (
            await db.execute(
                select(PushSyncConfig.tenant_id).where(PushSyncConfig.is_active.is_(True))
            )
        ).scalars().all()

    for tenant_id in configs:
        sync_push_labor.delay(str(tenant_id), job_type)

    logger.info("push_sync_dispatched", job_type=job_type, tenants=len(configs))
    return {"job_type": job_type, "tenants_dispatched": len(configs)}


@celery_app.task(
    name="push.sync_labor",
    bind=True,
    queue="sync",
    max_retries=3,
    default_retry_delay=300,
)
def sync_push_labor(self, tenant_id: str, job_type: str = "incremental") -> dict:
    from app.services.labor.push_client import PushAuthError

    try:
        return asyncio.run(_sync_async(uuid.UUID(tenant_id), job_type))
    except PushAuthError as exc:
        # A bad or unscoped token will not fix itself on retry — surface it
        # instead of burning the retry budget every 5 minutes.
        logger.error("push_sync_auth_failed", tenant_id=tenant_id, error=str(exc))
        raise


@celery_app.task(name="push.historical_import", queue="sync", max_retries=1)
def historical_import(tenant_id: str, start: str | None = None) -> dict:
    return asyncio.run(_historical_async(uuid.UUID(tenant_id), start))


async def _sync_async(tenant_id: uuid.UUID, job_type: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.labor.push_sync_service import (
        INCREMENTAL_LOOKBACK_DAYS,
        get_active_config,
        sync_range,
    )

    async with AsyncSessionLocal() as db:
        config = await get_active_config(db, tenant_id)
        if config is None:
            return {"skipped": "no active push config"}

        today = datetime.now(UTC).date()
        if job_type == "realtime":
            start = today
        else:
            start = today - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)

        job = await sync_range(db, tenant_id, config, start, today, job_type=job_type)
        await db.commit()
        return {
            "status": job.status,
            "rows_upserted": job.rows_upserted,
            "start": start.isoformat(),
            "end": today.isoformat(),
        }


async def _historical_async(tenant_id: uuid.UUID, start: str | None) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.labor.push_sync_service import (
        PUSH_IMPORT_SINCE,
        get_active_config,
        sync_range,
    )

    async with AsyncSessionLocal() as db:
        config = await get_active_config(db, tenant_id)
        if config is None:
            return {"skipped": "no active push config"}

        start_date = date.fromisoformat(start) if start else PUSH_IMPORT_SINCE
        today = datetime.now(UTC).date()
        job = await sync_range(db, tenant_id, config, start_date, today, job_type="historical")
        config.historical_import_complete = True
        config.historical_import_from = start_date
        await db.commit()
        return {"status": job.status, "rows_upserted": job.rows_upserted}
