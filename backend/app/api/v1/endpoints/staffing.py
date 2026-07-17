"""
Staffing tab endpoints — PushOperations labor data.

All figures come from push_labour_employee_daily (synced from the Push API,
see app.services.labor.push_sync_service). Tenant-scoped throughout; every
query filters on user.tenant_id and an optional location_id.
"""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, func, select

from app.core.deps import CurrentUserDep, ManagerDep
from app.db.models.push_labor import PushSyncConfig
from app.db.models.toast import ToastOrder
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


def _parse_range(date_from: str, date_to: str) -> tuple[date, date]:
    start = datetime.fromisoformat(date_from).date()
    end = datetime.fromisoformat(date_to).date()
    if start > end:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to")
    return start, end


@router.get("/summary", response_model=APIResponse[dict])
async def staffing_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """KPI header: total labor cost/hours over the range, plus net revenue for labor %."""
    from app.services.labor.push_sync_service import get_active_config, labor_totals

    config = await get_active_config(db, user.tenant_id)
    if config is None:
        return {"data": {"connected": False}, "errors": None}

    start, end = _parse_range(date_from, date_to)
    cost, hours = await labor_totals(db, user.tenant_id, start, end, location_id=location_id)

    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    net_rev = (
        await db.execute(
            select(func.sum(ToastOrder.net_amount)).where(
                and_(
                    ToastOrder.tenant_id == user.tenant_id,
                    ToastOrder.business_date >= start_str,
                    ToastOrder.business_date <= end_str,
                    ToastOrder.is_void.is_(False),
                    *([ToastOrder.location_id == location_id] if location_id else []),
                )
            )
        )
    ).scalar_one()
    net_revenue = float(net_rev) if net_rev is not None else None

    return {
        "data": {
            "connected": True,
            "labor_cost": float(cost),
            "labor_hours": float(hours),
            "avg_wage": float(cost / hours) if hours and hours > 0 else None,
            "net_revenue": net_revenue,
            "labor_pct_of_sales": round(float(cost) / net_revenue * 100, 1) if net_revenue else None,
            "last_synced_at": config.last_synced_at.isoformat() if config.last_synced_at else None,
            "historical_import_complete": config.historical_import_complete,
        },
        "errors": None,
    }


@router.get("/daily-trend", response_model=APIResponse[dict])
async def staffing_daily_trend(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(...),
    date_to: str = Query(...),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Daily labor cost + hours series, for the trend chart."""
    from app.services.labor.push_sync_service import labor_daily_series

    start, end = _parse_range(date_from, date_to)
    series = await labor_daily_series(db, user.tenant_id, start, end, location_id=location_id)
    return {
        "data": {
            "series": [
                {"date": row["date"], "cost": float(row["cost"]), "hours": float(row["hours"])}
                for row in series
            ]
        },
        "errors": None,
    }


@router.get("/by-position", response_model=APIResponse[dict])
async def staffing_by_position(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(...),
    date_to: str = Query(...),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Cost/hours grouped by position — the closest available breakdown to a
    department split; see push_sync_service.labor_by_position for why."""
    from app.services.labor.push_sync_service import labor_by_position

    start, end = _parse_range(date_from, date_to)
    rows = await labor_by_position(db, user.tenant_id, start, end, location_id=location_id)
    total = sum((r["cost"] for r in rows), Decimal("0"))
    return {
        "data": {
            "positions": [
                {
                    "position": r["position"],
                    "cost": float(r["cost"]),
                    "hours": float(r["hours"]),
                    "pct_of_total": round(float(r["cost"]) / float(total) * 100, 1) if total else None,
                }
                for r in rows
            ]
        },
        "errors": None,
    }


@router.get("/top-employees", response_model=APIResponse[dict])
async def staffing_top_employees(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(...),
    date_to: str = Query(...),
    location_id: uuid.UUID | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    from app.services.labor.push_sync_service import top_employees_by_cost

    start, end = _parse_range(date_from, date_to)
    rows = await top_employees_by_cost(db, user.tenant_id, start, end, location_id=location_id, limit=limit)
    return {
        "data": {
            "employees": [
                {
                    "employee_id": r["employee_id"],
                    "employee_name": r["employee_name"],
                    "position": r["position"],
                    "cost": float(r["cost"]),
                    "hours": float(r["hours"]),
                    "overtime_hours": float(r["overtime_hours"]),
                }
                for r in rows
            ]
        },
        "errors": None,
    }


@router.get("/today-team", response_model=APIResponse[dict])
async def staffing_today_team(
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    """Who's on shift today, live from Push (clock-in/out times, currently-in status)."""
    from app.services.labor.push_sync_service import push_local_today, today_team

    today = push_local_today()
    team = await today_team(db, user.tenant_id, today)
    if team is None:
        return {"data": {"connected": False, "team": []}, "errors": None}
    return {"data": {"connected": True, "business_date": today.isoformat(), "team": team}, "errors": None}


@router.get("/scheduled-vs-actual", response_model=APIResponse[dict])
async def staffing_scheduled_vs_actual(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(...),
    date_to: str = Query(...),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Scheduled hours (live from Push /shifts) vs actual hours per day. No
    dollar figure — see push_sync_service.scheduled_vs_actual_daily for why."""
    from app.services.labor.push_sync_service import scheduled_vs_actual_daily

    start, end = _parse_range(date_from, date_to)
    rows = await scheduled_vs_actual_daily(db, user.tenant_id, start, end, location_id=location_id)
    if rows is None:
        return {"data": {"connected": False, "days": []}, "errors": None}
    return {
        "data": {
            "connected": True,
            "days": [
                {
                    "date": r["date"],
                    "scheduled_hours": float(r["scheduled_hours"]),
                    "actual_hours": float(r["actual_hours"]),
                    "variance_hours": float(r["variance_hours"]),
                    "variance_pct": r["variance_pct"],
                }
                for r in rows
            ],
        },
        "errors": None,
    }


@router.get("/missed-clockouts", response_model=APIResponse[dict])
async def staffing_missed_clockouts(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    lookback_days: int = Query(3, ge=1, le=14),
) -> dict:
    """Punches that look like a forgotten clock-out (open past a full day, or
    open >14h same-day). See push_sync_service.missed_clockouts for tiers."""
    from app.services.labor.push_sync_service import missed_clockouts

    flags = await missed_clockouts(db, user.tenant_id, lookback_days=lookback_days)
    if flags is None:
        return {"data": {"connected": False, "flags": []}, "errors": None}
    return {"data": {"connected": True, "flags": flags}, "errors": None}


@router.get("/sync-status", response_model=APIResponse[dict])
async def staffing_sync_status(
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    from app.services.labor.push_sync_service import get_active_config

    config = await get_active_config(db, user.tenant_id)
    if config is None:
        return {"data": {"connected": False}, "errors": None}
    return {
        "data": {
            "connected": True,
            "company_name": config.push_company_name,
            "last_synced_at": config.last_synced_at.isoformat() if config.last_synced_at else None,
            "historical_import_complete": config.historical_import_complete,
            "historical_import_from": config.historical_import_from.isoformat()
            if config.historical_import_from
            else None,
        },
        "errors": None,
    }


@router.post("/sync-now", response_model=APIResponse[dict])
async def staffing_sync_now(
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    """Manual trailing-window sync — mirrors the incremental Beat schedule on demand."""
    from app.services.labor.push_sync_service import (
        INCREMENTAL_LOOKBACK_DAYS,
        get_active_config,
        push_local_today,
        sync_range,
    )

    config = await get_active_config(db, user.tenant_id)
    if config is None:
        raise HTTPException(status_code=400, detail="No active PushOperations integration for this tenant")

    today = push_local_today()
    start = today - timedelta(days=INCREMENTAL_LOOKBACK_DAYS)
    job = await sync_range(db, user.tenant_id, config, start, today, job_type="manual")
    await db.commit()
    return {
        "data": {"status": job.status, "rows_upserted": job.rows_upserted},
        "errors": None,
    }
