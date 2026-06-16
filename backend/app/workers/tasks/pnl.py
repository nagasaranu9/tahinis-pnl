"""P&L Celery tasks.

monthly_pnl_all_tenants — Beat entry (monthly), snapshots all tenants.
compute_pnl_snapshot     — Per-tenant per-location snapshot task.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from calendar import monthrange

import structlog

from app.db.session import get_db_context
from app.db.models.tenant import Tenant
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="pnl.compute_pnl_snapshot", bind=True, max_retries=3, default_retry_delay=300)
def compute_pnl_snapshot(
    self,
    tenant_id: str,
    year: int,
    month: int,
    location_id: str | None = None,
) -> None:
    asyncio.run(_compute_snapshot(tenant_id, year, month, location_id))


async def _compute_snapshot(
    tenant_id: str,
    year: int,
    month: int,
    location_id: str | None,
) -> None:
    from app.services.pnl.calculator import PnLCalculator
    from app.db.repositories.pnl_repo import PnLRepository

    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    period_end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    period_label = f"{year:04d}-{month:02d}"

    async with get_db_context() as db:
        calculator = PnLCalculator(db)
        repo = PnLRepository(db)

        report = await calculator.compute(
            tenant_id=uuid.UUID(tenant_id),
            period_start=period_start,
            period_end=period_end,
            location_id=uuid.UUID(location_id) if location_id else None,
        )
        await repo.upsert_snapshot(report, period_label=period_label)
        await db.commit()

    logger.info("pnl_snapshot_saved", tenant_id=tenant_id, period_label=period_label)


@celery_app.task(name="pnl.monthly_pnl_all_tenants")
def monthly_pnl_all_tenants() -> None:
    """Celery Beat entry — snapshot previous month for all active tenants."""
    asyncio.run(_monthly_all())


async def _monthly_all() -> None:
    from sqlalchemy import select

    async with get_db_context() as db:
        # Snapshot previous calendar month
        today = datetime.now(timezone.utc)
        first_of_month = today.replace(day=1)
        prev_month_end = first_of_month - timedelta(days=1)
        year, month = prev_month_end.year, prev_month_end.month

        rows = await db.execute(select(Tenant))
        tenants = rows.scalars().all()

    for tenant in tenants:
        compute_pnl_snapshot.apply_async(
            kwargs={
                "tenant_id": str(tenant.id),
                "year": year,
                "month": month,
                "location_id": None,
            },
            queue="default",
        )
    logger.info("monthly_pnl_dispatched", count=len(tenants), year=year, month=month)
