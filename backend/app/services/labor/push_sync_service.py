"""
PushOperations labor sync.

Pulls employee-grain daily labour from the Push API and upserts it into
`push_labour_employee_daily`. Every write is keyed on
(tenant, company, business_date, employee, position, labour_type) so a re-sync
of any range corrects rows in place. That matters because managers fix missed
clock-outs in Push days after the fact — the incremental sync deliberately
re-pulls a trailing window to absorb those edits.

Aggregation for the P&L lives in `labor_totals`, which is the single place the
Labor Cost line is derived from once the integration is active.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.push_labor import (
    LABOUR_TYPE_OVERTIME,
    PushLabourEmployeeDaily,
    PushSyncConfig,
    PushSyncJob,
)
from app.services.labor.push_client import LabourRow, PushClient, iter_date_chunks

logger = structlog.get_logger(__name__)

# The operator's Push data begins here; earlier dates return empty.
PUSH_IMPORT_SINCE = date(2026, 1, 1)

# Incremental syncs re-pull this many trailing days so retroactive punch edits
# and late payroll adjustments land without a full backfill.
INCREMENTAL_LOOKBACK_DAYS = 7


async def get_active_config(db: AsyncSession, tenant_id: uuid.UUID) -> PushSyncConfig | None:
    """The tenant's active Push config, or None when the integration is off."""
    return (
        await db.execute(
            select(PushSyncConfig).where(
                PushSyncConfig.tenant_id == tenant_id,
                PushSyncConfig.is_active.is_(True),
            )
        )
    ).scalars().first()


async def _upsert_rows(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    location_id: uuid.UUID | None,
    push_company_id: int,
    rows: list[LabourRow],
) -> int:
    if not rows:
        return 0

    payload = [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "location_id": location_id,
            "push_company_id": push_company_id,
            "business_date": r.business_date,
            "employee_id": r.employee_id,
            "employee_name": r.employee_name,
            "position_id": r.position_id,
            "position_name": r.position_name,
            "labour_type": r.labour_type,
            "cost": r.cost,
            "hours": r.hours,
        }
        for r in rows
    ]

    stmt = pg_insert(PushLabourEmployeeDaily).values(payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_push_labour_employee_daily",
        set_={
            "cost": stmt.excluded.cost,
            "hours": stmt.excluded.hours,
            "employee_name": stmt.excluded.employee_name,
            "position_name": stmt.excluded.position_name,
            "location_id": stmt.excluded.location_id,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    return len(payload)


async def sync_range(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    config: PushSyncConfig,
    start: date,
    end: date,
    job_type: str = "manual",
) -> PushSyncJob:
    """
    Pull and upsert labour for [start, end], chunked to the API's 2-day limit.

    Records a PushSyncJob for auditability whether the run succeeds or fails.
    """
    job = PushSyncJob(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        push_company_id=config.push_company_id,
        job_type=job_type,
        status="running",
        period_start=start,
        period_end=end,
        started_at=datetime.now(UTC),
    )
    db.add(job)
    await db.flush()

    total = 0
    try:
        async with PushClient(
            company_id=config.push_company_id, company_uuid=config.push_company_uuid
        ) as client:
            for chunk_start, chunk_end in iter_date_chunks(start, end):
                rows = await client.get_labour_by_employee(chunk_start, chunk_end)
                total += await _upsert_rows(
                    db, tenant_id, config.location_id, config.push_company_id, rows
                )
                logger.info(
                    "push_labour_chunk_synced",
                    tenant_id=str(tenant_id),
                    start=chunk_start.isoformat(),
                    end=chunk_end.isoformat(),
                    rows=len(rows),
                )
        job.status = "succeeded"
        job.rows_upserted = total
        config.last_synced_at = datetime.now(UTC)
    except Exception as exc:
        job.status = "failed"
        job.error_message = str(exc)[:1000]
        logger.error(
            "push_labour_sync_failed",
            tenant_id=str(tenant_id),
            start=start.isoformat(),
            end=end.isoformat(),
            error=str(exc),
        )
        raise
    finally:
        job.finished_at = datetime.now(UTC)
        await db.flush()

    return job


async def labor_totals(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    location_id: uuid.UUID | None = None,
) -> tuple[Decimal, Decimal]:
    """
    Total labor cost and hours from Push for [start, end] inclusive.

    This is the Labor Cost figure the P&L uses when the Push integration is
    active. Returns (Decimal("0.00"), Decimal("0.00")) when there is no data,
    which the caller must distinguish from "integration inactive" — see
    PnLCalculator, which checks for an active config before calling this.
    """
    q = select(
        func.coalesce(func.sum(PushLabourEmployeeDaily.cost), 0),
        func.coalesce(func.sum(PushLabourEmployeeDaily.hours), 0),
    ).where(
        PushLabourEmployeeDaily.tenant_id == tenant_id,
        PushLabourEmployeeDaily.business_date >= start,
        PushLabourEmployeeDaily.business_date <= end,
    )
    if location_id is not None:
        q = q.where(PushLabourEmployeeDaily.location_id == location_id)
    cost, hours = (await db.execute(q)).one()
    return Decimal(str(cost)), Decimal(str(hours))


async def labor_by_position(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    location_id: uuid.UUID | None = None,
) -> list[dict]:
    """Cost + hours grouped by position for [start, end] inclusive.

    Position stands in for department: the token scope for this tenant does
    not include /departments or /analytics/summary/labour-actuals (both return
    "Insufficient permissions"), and costCenterName comes back empty on every
    row — so position is the only grouping dimension actually available.
    """
    q = (
        select(
            PushLabourEmployeeDaily.position_name,
            func.sum(PushLabourEmployeeDaily.cost),
            func.sum(PushLabourEmployeeDaily.hours),
        )
        .where(
            PushLabourEmployeeDaily.tenant_id == tenant_id,
            PushLabourEmployeeDaily.business_date >= start,
            PushLabourEmployeeDaily.business_date <= end,
        )
        .group_by(PushLabourEmployeeDaily.position_name)
        .order_by(func.sum(PushLabourEmployeeDaily.cost).desc())
    )
    if location_id is not None:
        q = q.where(PushLabourEmployeeDaily.location_id == location_id)
    rows = (await db.execute(q)).all()
    return [
        {
            "position": name or "Unassigned",
            "cost": Decimal(str(cost or 0)),
            "hours": Decimal(str(hours or 0)),
        }
        for name, cost, hours in rows
    ]


async def labor_daily_series(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    location_id: uuid.UUID | None = None,
) -> list[dict]:
    """Cost + hours per business_date for [start, end] inclusive — trend chart source."""
    q = (
        select(
            PushLabourEmployeeDaily.business_date,
            func.sum(PushLabourEmployeeDaily.cost),
            func.sum(PushLabourEmployeeDaily.hours),
        )
        .where(
            PushLabourEmployeeDaily.tenant_id == tenant_id,
            PushLabourEmployeeDaily.business_date >= start,
            PushLabourEmployeeDaily.business_date <= end,
        )
        .group_by(PushLabourEmployeeDaily.business_date)
        .order_by(PushLabourEmployeeDaily.business_date)
    )
    if location_id is not None:
        q = q.where(PushLabourEmployeeDaily.location_id == location_id)
    rows = (await db.execute(q)).all()
    return [
        {"date": d.isoformat(), "cost": Decimal(str(cost or 0)), "hours": Decimal(str(hours or 0))}
        for d, cost, hours in rows
    ]


async def top_employees_by_cost(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    location_id: uuid.UUID | None = None,
    limit: int = 10,
) -> list[dict]:
    """Top employees by total cost for [start, end], with overtime hours broken out."""
    q = (
        select(
            PushLabourEmployeeDaily.employee_id,
            PushLabourEmployeeDaily.employee_name,
            PushLabourEmployeeDaily.position_name,
            func.sum(PushLabourEmployeeDaily.cost),
            func.sum(PushLabourEmployeeDaily.hours),
            func.sum(
                case(
                    (PushLabourEmployeeDaily.labour_type.in_(list(LABOUR_TYPE_OVERTIME)), PushLabourEmployeeDaily.hours),
                    else_=0,
                )
            ),
        )
        .where(
            PushLabourEmployeeDaily.tenant_id == tenant_id,
            PushLabourEmployeeDaily.business_date >= start,
            PushLabourEmployeeDaily.business_date <= end,
        )
        .group_by(
            PushLabourEmployeeDaily.employee_id,
            PushLabourEmployeeDaily.employee_name,
            PushLabourEmployeeDaily.position_name,
        )
        .order_by(func.sum(PushLabourEmployeeDaily.cost).desc())
        .limit(limit)
    )
    if location_id is not None:
        q = q.where(PushLabourEmployeeDaily.location_id == location_id)
    rows = (await db.execute(q)).all()
    return [
        {
            "employee_id": emp_id,
            "employee_name": name,
            "position": position or "Unassigned",
            "cost": Decimal(str(cost or 0)),
            "hours": Decimal(str(hours or 0)),
            "overtime_hours": Decimal(str(ot_hours or 0)),
        }
        for emp_id, name, position, cost, hours, ot_hours in rows
    ]
