import asyncio
import uuid
from datetime import datetime

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    base=TrackedTask,
    bind=True,
    name="app.workers.tasks.reconciliation.run_reconciliation",
    queue="default",
    max_retries=2,
    default_retry_delay=60,
)
def run_reconciliation(
    self,  # type: ignore[misc]
    run_id: str,
    tenant_id: str,
    period_start: str,
    period_end: str,
    location_id: str | None = None,
) -> dict:
    return asyncio.run(_run_async(run_id, tenant_id, period_start, period_end, location_id))


async def _run_async(
    run_id_str: str,
    tenant_id_str: str,
    period_start_str: str,
    period_end_str: str,
    location_id_str: str | None,
) -> dict:
    from app.db.session import AsyncSessionLocal
    from app.services.reconciliation.engine import ReconciliationEngine

    run_id = uuid.UUID(run_id_str)
    tenant_id = uuid.UUID(tenant_id_str)
    period_start = datetime.fromisoformat(period_start_str)
    period_end = datetime.fromisoformat(period_end_str)
    location_id = uuid.UUID(location_id_str) if location_id_str else None

    async with AsyncSessionLocal() as db:
        engine = ReconciliationEngine(db)
        await engine.run(
            run_id=run_id,
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
            location_id=location_id,
        )

    return {"status": "complete", "run_id": run_id_str}


@celery_app.task(
    base=TrackedTask,
    bind=True,
    name="app.workers.tasks.reconciliation.weekly_reconciliation_all_tenants",
    queue="default",
)
def weekly_reconciliation_all_tenants(self) -> None:  # type: ignore[misc]
    """Beat entry: trigger weekly reconciliation for all active tenants."""
    asyncio.run(_weekly_async())


async def _weekly_async() -> None:
    from datetime import UTC, timedelta

    from app.db.models.tenant import Tenant
    from app.db.session import AsyncSessionLocal
    from app.db.repositories.reconciliation_repo import ReconciliationRepository
    from sqlalchemy import select

    now = datetime.now(UTC)
    period_end = now
    period_start = now - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        tenants = (await db.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
        repo = ReconciliationRepository(db)
        for tenant in tenants:
            run = await repo.create_run(
                tenant_id=tenant.id,
                period_start=period_start,
                period_end=period_end,
                triggered_by=tenant.id,  # system-triggered
            )
            await db.commit()
            run_reconciliation.apply_async(
                kwargs={
                    "run_id": str(run.id),
                    "tenant_id": str(tenant.id),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                },
                queue="default",
            )
