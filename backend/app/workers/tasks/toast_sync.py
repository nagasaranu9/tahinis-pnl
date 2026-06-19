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
    """Entry point — kicks off the first month chunk (rest chain themselves)."""
    return asyncio.run(_run_historical_chunk(tenant_id, location_id, job_id, None))


@celery_app.task(
    bind=True,
    base=TrackedTask,
    name="toast.historical_chunk",
    queue="sync",
    max_retries=3,
    default_retry_delay=300,
)
def toast_historical_chunk(
    self, tenant_id: str, location_id: str, job_id: str, cursor_iso: Optional[str]
) -> dict:
    """Sync one month-window, then chain the next. Each chunk is independent."""
    return asyncio.run(_run_historical_chunk(tenant_id, location_id, job_id, cursor_iso))


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


async def _run_historical_chunk(
    tenant_id: str, location_id: str, job_id: str, cursor_iso: Optional[str]
) -> dict:
    """Process one month-window. Chain next chunk if more remain; else complete."""
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.toast_repo import ToastRepository
    from app.services.toast.sync_service import ToastSyncService

    t_id = uuid.UUID(tenant_id)
    l_id = uuid.UUID(location_id)
    j_id = uuid.UUID(job_id)
    cursor = datetime.fromisoformat(cursor_iso) if cursor_iso else None

    redis_client = await _get_redis()
    try:
        async with AsyncSessionLocal() as db:
            repo = ToastRepository(db)
            # Mark running on the first chunk only.
            if cursor is None:
                await repo.update_job_status(j_id, "running", started_at=datetime.now(UTC))
                await db.commit()
            try:
                svc = ToastSyncService(db)
                result = await svc.run_historical_chunk(
                    t_id, l_id, j_id, cursor=cursor, redis_client=redis_client
                )
                if result["done"]:
                    await repo.update_job_status(j_id, "complete", completed_at=datetime.now(UTC))
                    await db.commit()
                else:
                    # Chain the next month as its own task → short, restart-safe.
                    next_cursor = result["next_cursor"]
                    toast_historical_chunk.apply_async(
                        args=[tenant_id, location_id, job_id, next_cursor.isoformat()],
                        queue="sync",
                    )
                return result["counts"]
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

    from datetime import timedelta
    from sqlalchemy import select, func, update
    from app.db.models.toast import ToastSyncJob

    dispatched = 0
    async with AsyncSessionLocal() as db:
        # Expire stale pending/running jobs: a healthy worker grabs a queued job
        # within seconds, so anything still pending after 10 min is an orphan
        # left by a worker that died mid-flight (its Redis message is gone). Mark
        # them failed so they stop blocking new dispatch and show honestly in UI.
        # Only sweep incremental jobs: historical imports chain month-by-month and
        # legitimately stay "running" for well over an hour. Killing them here was
        # marking healthy backfills as stale mid-flight.
        stale_cutoff = datetime.now(UTC) - timedelta(minutes=60)
        await db.execute(
            update(ToastSyncJob)
            .where(
                ToastSyncJob.status.in_(("pending", "running")),
                ToastSyncJob.job_type == "incremental",
                ToastSyncJob.created_at < stale_cutoff,
            )
            .values(status="failed", error_message="Timed out — worker did not process (stale)")
        )
        await db.commit()

        repo = ToastRepository(db)
        configs = await repo.list_active_configs()
        for config in configs:
            # Skip if an incremental job is already pending/running for this
            # location — otherwise a down/slow worker lets per-minute beat ticks
            # pile up hundreds of orphan "pending" rows that never drain.
            backlog = (await db.execute(
                select(func.count(ToastSyncJob.id)).where(
                    ToastSyncJob.tenant_id == config.tenant_id,
                    ToastSyncJob.location_id == config.location_id,
                    ToastSyncJob.job_type == "incremental",
                    ToastSyncJob.status.in_(("pending", "running")),
                )
            )).scalar_one()
            if backlog and backlog > 0:
                logger.info(
                    "toast_dispatch_skipped_backlog",
                    location_id=str(config.location_id),
                    backlog=backlog,
                )
                continue
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
