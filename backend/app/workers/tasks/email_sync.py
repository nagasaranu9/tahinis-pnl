import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True, base=TrackedTask, name="email.gmail_sync_all",
    queue="sync",
)
def gmail_sync_all(self) -> dict:
    return asyncio.run(_dispatch_email_sync("gmail"))


@celery_app.task(
    bind=True, base=TrackedTask, name="email.outlook_sync_all",
    queue="sync",
)
def outlook_sync_all(self) -> dict:
    return asyncio.run(_dispatch_email_sync("outlook"))


@celery_app.task(
    bind=True, base=TrackedTask, name="email.gmail_historical_import_single",
    queue="sync", max_retries=1, default_retry_delay=600,
)
def gmail_historical_import_single(self, tenant_id: str, config_id: str, job_id: str, after_date: str) -> dict:
    return asyncio.run(
        _run_gmail_historical(tenant_id, config_id, job_id, after_date)
    )


@celery_app.task(
    bind=True, base=TrackedTask, name="email.gmail_sync_single",
    queue="sync", max_retries=3, default_retry_delay=300,
)
def gmail_sync_single(self, tenant_id: str, config_id: str, job_id: str) -> dict:
    return asyncio.run(
        _run_email_sync("gmail", tenant_id, config_id, job_id)
    )


@celery_app.task(
    bind=True, base=TrackedTask, name="email.outlook_sync_single",
    queue="sync", max_retries=3, default_retry_delay=300,
)
def outlook_sync_single(self, tenant_id: str, config_id: str, job_id: str) -> dict:
    return asyncio.run(
        _run_email_sync("outlook", tenant_id, config_id, job_id)
    )


# ------------------------------------------------------------------
# Async implementations
# ------------------------------------------------------------------

async def _dispatch_email_sync(provider: str) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.email_repo import EmailSyncRepository

    dispatched = 0
    async with AsyncSessionLocal() as db:
        repo = EmailSyncRepository(db)
        configs = await repo.list_all_active_configs()
        for config in [c for c in configs if c.provider == provider]:
            job = await repo.create_job(
                tenant_id=config.tenant_id,
                config_id=config.id,
                provider=provider,
            )
            await db.commit()

            task_fn = gmail_sync_single if provider == "gmail" else outlook_sync_single
            task_fn.apply_async(
                args=[str(config.tenant_id), str(config.id), str(job.id)],
                queue="sync",
            )
            dispatched += 1

    logger.info("email_dispatch_complete", provider=provider, dispatched=dispatched)
    return {"dispatched": dispatched, "provider": provider}


async def _run_email_sync(
    provider: str, tenant_id: str, config_id: str, job_id: str
) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.email_repo import EmailSyncRepository
    from app.services.email.processing_service import EmailSyncService

    t_id = uuid.UUID(tenant_id)
    c_id = uuid.UUID(config_id)
    j_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        repo = EmailSyncRepository(db)
        await repo.update_job(j_id, "running", started_at=datetime.now(UTC))
        await db.commit()

        config = await repo.get_config_by_id(t_id, c_id)
        if not config:
            await repo.update_job(j_id, "failed", error_message="Config not found")
            await db.commit()
            return {}

        try:
            svc = EmailSyncService(db)
            if provider == "gmail":
                counts = await svc.sync_gmail(t_id, config, j_id)
            else:
                counts = await svc.sync_outlook(t_id, config, j_id)

            await repo.update_job(j_id, "complete", completed_at=datetime.now(UTC), **counts)
            await db.commit()
            return counts
        except Exception as exc:
            await repo.update_job(
                j_id, "failed",
                completed_at=datetime.now(UTC),
                error_message=str(exc)[:1000],
            )
            await db.commit()
            raise


async def _run_gmail_historical(
    tenant_id: str, config_id: str, job_id: str, after_date: str
) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.email_repo import EmailSyncRepository
    from app.services.email.processing_service import EmailSyncService

    t_id = uuid.UUID(tenant_id)
    c_id = uuid.UUID(config_id)
    j_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        repo = EmailSyncRepository(db)
        await repo.update_job(j_id, "running", started_at=datetime.now(UTC))
        await db.commit()

        config = await repo.get_config_by_id(t_id, c_id)
        if not config:
            await repo.update_job(j_id, "failed", error_message="Config not found")
            await db.commit()
            return {}

        try:
            svc = EmailSyncService(db)
            counts = await svc.sync_gmail_historical(t_id, config, j_id, after_date)
            await repo.update_job(j_id, "complete", completed_at=datetime.now(UTC), **counts)
            await db.commit()
            return counts
        except Exception as exc:
            await repo.update_job(
                j_id, "failed",
                completed_at=datetime.now(UTC),
                error_message=str(exc)[:1000],
            )
            await db.commit()
            raise
