import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True, base=TrackedTask, name="drive.gdrive_sync_all",
    queue="sync",
)
def gdrive_sync_all(self) -> dict:
    return asyncio.get_event_loop().run_until_complete(_dispatch_drive_sync())


@celery_app.task(
    bind=True, base=TrackedTask, name="drive.gdrive_sync_single",
    queue="sync", max_retries=3, default_retry_delay=300,
)
def gdrive_sync_single(self, tenant_id: str, config_id: str, job_id: str) -> dict:
    return asyncio.get_event_loop().run_until_complete(
        _run_drive_sync(tenant_id, config_id, job_id)
    )


async def _dispatch_drive_sync() -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.email_repo import EmailSyncRepository

    dispatched = 0
    async with AsyncSessionLocal() as db:
        repo = EmailSyncRepository(db)
        configs = await repo.list_all_active_drive_configs()
        for config in configs:
            job = await repo.create_drive_job(
                tenant_id=config.tenant_id,
                config_id=config.id,
            )
            await db.commit()
            gdrive_sync_single.apply_async(
                args=[str(config.tenant_id), str(config.id), str(job.id)],
                queue="sync",
            )
            dispatched += 1

    logger.info("gdrive_dispatch_complete", dispatched=dispatched)
    return {"dispatched": dispatched}


async def _run_drive_sync(tenant_id: str, config_id: str, job_id: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.email_repo import EmailSyncRepository
    from app.services.email.processing_service import EmailSyncService

    t_id = uuid.UUID(tenant_id)
    c_id = uuid.UUID(config_id)
    j_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        repo = EmailSyncRepository(db)
        await repo.update_drive_job(j_id, "running", started_at=datetime.now(UTC))
        await db.commit()

        from sqlalchemy import select
        from app.db.models.email_sync import DriveSyncConfig
        config = (await db.execute(
            select(DriveSyncConfig).where(
                DriveSyncConfig.tenant_id == t_id,
                DriveSyncConfig.id == c_id,
            )
        )).scalar_one_or_none()

        if not config:
            await repo.update_drive_job(j_id, "failed", error_message="Config not found")
            await db.commit()
            return {}

        try:
            svc = EmailSyncService(db)
            counts = await svc.sync_drive(t_id, config, j_id)
            await repo.update_drive_job(j_id, "complete", completed_at=datetime.now(UTC), **counts)
            await db.commit()
            return counts
        except Exception as exc:
            await repo.update_drive_job(
                j_id, "failed",
                completed_at=datetime.now(UTC),
                error_message=str(exc)[:1000],
            )
            await db.commit()
            raise
