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
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

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

# Push's business_date and clock timestamps are restaurant-local, not UTC.
# Deriving "today" from UTC is wrong for several hours a day (America/Toronto
# is UTC-4/-5) — e.g. 9pm local is already the next UTC day.
PUSH_LOCAL_TIMEZONE = "America/Toronto"


def push_local_today() -> date:
    return datetime.now(ZoneInfo(PUSH_LOCAL_TIMEZONE)).date()


def push_local_now_naive() -> datetime:
    """Current local time, tzinfo stripped to compare against naive Push timestamps."""
    return datetime.now(ZoneInfo(PUSH_LOCAL_TIMEZONE)).replace(tzinfo=None)


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


async def today_team(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    business_date: date,
) -> list[dict] | None:
    """
    Who's on shift today, live from Push — not persisted.

    Punches are a handful of rows/day (unlike the historical labour dataset),
    and this needs to be current-second-accurate for "who's clocked in right
    now", so it calls the API directly on every request instead of going
    through the upsert table. Returns None when there is no active config.
    """
    from app.services.labor.push_client import PushClient

    config = await get_active_config(db, tenant_id)
    if config is None:
        return None

    async with PushClient(
        company_id=config.push_company_id, company_uuid=config.push_company_uuid
    ) as client:
        rows = await client.get_clocks(business_date, business_date)

    return [
        {
            "employee_id": r.employee_id,
            "employee_name": r.employee_name,
            "position": r.position_name or "Unassigned",
            "clock_in": r.clock_in.isoformat() if r.clock_in else None,
            "clock_out": r.clock_out.isoformat() if r.clock_out else None,
            "is_clocked_in": r.is_current,
        }
        for r in sorted(rows, key=lambda r: (not r.is_current, r.clock_in or datetime.min))
    ]


async def scheduled_vs_actual_daily(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    start: date,
    end: date,
    location_id: uuid.UUID | None = None,
) -> list[dict] | None:
    """
    Scheduled hours (live from /shifts) vs actual hours (stored, from clock
    punches) per business date.

    Hours only, not dollars: Push does not expose a reliable per-employee wage
    rate to this token's scope, so a scheduled-cost figure would be a guess.
    Hours variance is the honest, available signal — a day scheduled for 40h
    that actually ran 55h is real overspend regardless of wage precision.
    """
    from app.services.labor.push_client import PushClient

    config = await get_active_config(db, tenant_id)
    if config is None:
        return None

    async with PushClient(
        company_id=config.push_company_id, company_uuid=config.push_company_uuid
    ) as client:
        shifts = await client.get_shifts(start, end)

    scheduled_by_date: dict[date, Decimal] = {}
    for s in shifts:
        scheduled_by_date[s.business_date] = scheduled_by_date.get(s.business_date, Decimal("0")) + s.scheduled_hours

    actual_series = await labor_daily_series(db, tenant_id, start, end, location_id=location_id)
    actual_by_date = {date.fromisoformat(row["date"]): row["hours"] for row in actual_series}

    all_dates = sorted(set(scheduled_by_date) | set(actual_by_date))
    result = []
    for d in all_dates:
        scheduled = scheduled_by_date.get(d, Decimal("0"))
        actual = actual_by_date.get(d, Decimal("0"))
        variance = actual - scheduled
        result.append(
            {
                "date": d.isoformat(),
                "scheduled_hours": scheduled,
                "actual_hours": actual,
                "variance_hours": variance,
                "variance_pct": round(float(variance) / float(scheduled) * 100, 1) if scheduled else None,
            }
        )
    return result


# An open punch from a prior business day is unambiguous — nobody has legitimately
# been clocked in since yesterday or earlier. A same-day punch older than this is
# a same-day candidate: still possibly a live long shift, so surfaced as a lower-
# confidence flag rather than a hard alert.
_SAME_DAY_OPEN_PUNCH_HOURS = 14


async def missed_clockouts(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    lookback_days: int = 3,
) -> list[dict] | None:
    """
    Punches that look like a forgotten clock-out rather than a real open shift.

    Two tiers:
    - "prior_day": is_current and business_date is before today — certain, no
      legitimate reason a punch from an earlier business day is still open.
    - "long_open": is_current, business_date is today, but clock_in is more
      than _SAME_DAY_OPEN_PUNCH_HOURS ago — likely forgotten, could still be a
      genuine long shift, so lower confidence.
    """
    from app.services.labor.push_client import PushClient

    config = await get_active_config(db, tenant_id)
    if config is None:
        return None

    today = push_local_today()
    start = today - timedelta(days=lookback_days)

    async with PushClient(
        company_id=config.push_company_id, company_uuid=config.push_company_uuid
    ) as client:
        rows = await client.get_clocks(start, today)

    now = push_local_now_naive()
    flagged = []
    for r in rows:
        if not r.is_current or r.clock_in is None:
            continue
        if r.business_date < today:
            tier = "prior_day"
        else:
            hours_open = (now - r.clock_in).total_seconds() / 3600
            if hours_open < _SAME_DAY_OPEN_PUNCH_HOURS:
                continue
            tier = "long_open"
        flagged.append(
            {
                "employee_id": r.employee_id,
                "employee_name": r.employee_name,
                "position": r.position_name or "Unassigned",
                "business_date": r.business_date.isoformat(),
                "clock_in": r.clock_in.isoformat(),
                "tier": tier,
            }
        )
    return sorted(flagged, key=lambda f: f["clock_in"])
