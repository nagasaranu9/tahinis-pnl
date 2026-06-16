import asyncio
import uuid
from datetime import UTC, datetime
from typing import Optional

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="toast.incremental_sync",
    queue="sync",
    max_retries=3,
    default_retry_delay=300,
)
def toast_incremental_sync(self, tenant_id: str, location_id: str, job_id: str) -> dict:
    """Incremental Toast sync for a single location."""
    return asyncio.run(
        _run_incremental(tenant_id, location_id, job_id)
    )


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="toast.historical_import",
    queue="sync",
    max_retries=2,
    default_retry_delay=600,
)
def toast_historical_import(self, tenant_id: str, location_id: str, job_id: str) -> dict:
    """One-shot historical import chunked by month."""
    return asyncio.run(
        _run_historical(tenant_id, location_id, job_id)
    )


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="toast.daily_sync_all_locations",
    queue="sync",
)
def toast_daily_sync_all_locations(self) -> dict:
    """Beat entry point — dispatches per-location incremental sync tasks."""
    return asyncio.run(_dispatch_daily_sync())


# kept for backward compat with Beat schedule defined in celery_beat.py
run_all_tenants = toast_daily_sync_all_locations


# ------------------------------------------------------------------
# Async implementations
# ------------------------------------------------------------------

async def _get_redis():
    """Get async Redis client for token caching."""
    try:
        import redis.asyncio as aioredis
        from app.core.config import settings
        return aioredis.from_url(str(settings.REDIS_URL), decode_responses=False)
    except Exception:
        return None


async def _run_incremental(tenant_id: str, location_id: str, job_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.toast_repo import ToastRepository
    from app.services.toast.sync_service import ToastSyncService

    t_id = uuid.UUID(tenant_id)
    l_id = uuid.UUID(location_id)
    j_id = uuid.UUID(job_id)

    redis_client = await _get_redis()
    try:
        async with AsyncSessionLocal() as db:
            repo = ToastRepository(db)
            await repo.update_job_status(j_id, "running", started_at=datetime.now(UTC))
            await db.commit()
            try:
                svc = ToastSyncService(db)
                counts = await svc.run_incremental_sync(t_id, l_id, j_id, redis_client=redis_client)
                await repo.update_job_status(j_id, "complete", completed_at=datetime.now(UTC), **counts)
                await db.commit()
                return counts
            except Exception as exc:
                await repo.update_job_status(
                    j_id, "failed", completed_at=datetime.now(UTC), error_message=str(exc)[:1000]
                )
                await db.commit()
                raise
    finally:
        if redis_client:
            await redis_client.aclose()


async def _run_historical(tenant_id: str, location_id: str, job_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.toast_repo import ToastRepository
    from app.services.toast.sync_service import ToastSyncService

    t_id = uuid.UUID(tenant_id)
    l_id = uuid.UUID(location_id)
    j_id = uuid.UUID(job_id)

    redis_client = await _get_redis()
    try:
        async with AsyncSessionLocal() as db:
            repo = ToastRepository(db)
            await repo.update_job_status(j_id, "running", started_at=datetime.now(UTC))
            await db.commit()
            try:
                svc = ToastSyncService(db)
                counts = await svc.run_historical_import(t_id, l_id, j_id, redis_client=redis_client)
                await repo.update_job_status(j_id, "complete", completed_at=datetime.now(UTC), **counts)
                await db.commit()
                return counts
            except Exception as exc:
                await repo.update_job_status(
                    j_id, "failed", completed_at=datetime.now(UTC), error_message=str(exc)[:1000]
                )
                await db.commit()
                raise
    finally:
        if redis_client:
            await redis_client.aclose()


async def _dispatch_daily_sync() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.toast_repo import ToastRepository

    dispatched = 0
    async with AsyncSessionLocal() as db:
        repo = ToastRepository(db)
        configs = await repo.list_active_configs()
        for config in configs:
            job = await repo.create_sync_job(
                tenant_id=config.tenant_id,
                location_id=config.location_id,
                job_type="incremental",
                date_from=config.last_synced_at,
                date_to=datetime.now(UTC),
            )
            await db.commit()
            toast_incremental_sync.apply_async(
                args=[str(config.tenant_id), str(config.location_id), str(job.id)],
                queue="sync",
            )
            dispatched += 1

    logger.info("toast_daily_dispatch_complete", dispatched=dispatched)
    return {"dispatched": dispatched}
