"""Dashboard aggregation endpoints.

Operational tiles for the redesigned dashboard that aren't covered by the P&L
report: revenue-by-channel and fulfillment time (from Toast order data), top
supplier per expense category, and a simple run-rate cash-flow projection.

All queries are tenant-scoped (mandatory) and optionally location-scoped.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import and_, func, select

from app.core.deps import CurrentUserDep
from app.db.models.expense import Expense
from app.db.models.toast import ToastOrder
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


def _parse_range(date_from: str, date_to: str) -> tuple[datetime, datetime]:
    start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(date_to).replace(
        hour=23, minute=59, second=59, tzinfo=timezone.utc
    )
    return start, end


def _toast_filters(user: CurrentUserDep, location_id: uuid.UUID | None,
                   start: datetime, end: datetime) -> list:
    conds = [
        ToastOrder.tenant_id == user.tenant_id,
        ToastOrder.opened_at >= start,
        ToastOrder.opened_at <= end,
        ToastOrder.is_void == False,  # noqa: E712
    ]
    if location_id is not None:
        conds.append(ToastOrder.location_id == location_id)
    return conds


@router.get("/channel-mix", response_model=APIResponse[dict])
async def channel_mix(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Revenue split by Toast dining option (TakeOut / Dine-in / Delivery / …)."""
    start, end = _parse_range(date_from, date_to)

    rows = (await db.execute(
        select(
            func.coalesce(ToastOrder.dining_option, "Unknown").label("channel"),
            func.coalesce(func.sum(ToastOrder.net_amount), 0).label("revenue"),
            func.count(ToastOrder.id).label("order_count"),
        )
        .where(and_(*_toast_filters(user, location_id, start, end)))
        .group_by(func.coalesce(ToastOrder.dining_option, "Unknown"))
    )).all()

    total = sum(float(r.revenue or 0) for r in rows) or 0.0
    channels = sorted(
        (
            {
                "channel": r.channel,
                "revenue": round(float(r.revenue or 0), 2),
                "order_count": r.order_count,
                "pct": round(float(r.revenue or 0) / total * 100, 1) if total > 0 else 0.0,
            }
            for r in rows
        ),
        key=lambda c: c["revenue"],
        reverse=True,
    )
    return {"data": {"total_revenue": round(total, 2), "channels": channels}, "errors": None}


@router.get("/fulfillment", response_model=APIResponse[dict])
async def fulfillment_time(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
    target_seconds: int = Query(480, description="Target fulfillment seconds (default 8 min)"),
) -> dict:
    """Average order fulfillment time (opened_at → closed_at), overall + by channel.

    Only orders with both timestamps and a positive duration count."""
    start, end = _parse_range(date_from, date_to)

    duration = func.extract("epoch", ToastOrder.closed_at - ToastOrder.opened_at)
    base_conds = _toast_filters(user, location_id, start, end) + [
        ToastOrder.closed_at.isnot(None),
        ToastOrder.opened_at.isnot(None),
        ToastOrder.closed_at > ToastOrder.opened_at,
    ]

    overall = (await db.execute(
        select(
            func.avg(duration).label("avg_s"),
            func.min(duration).label("min_s"),
            func.max(duration).label("max_s"),
            func.count(ToastOrder.id).label("n"),
        ).where(and_(*base_conds))
    )).one()

    by_channel_rows = (await db.execute(
        select(
            func.coalesce(ToastOrder.dining_option, "Unknown").label("channel"),
            func.avg(duration).label("avg_s"),
            func.count(ToastOrder.id).label("n"),
        )
        .where(and_(*base_conds))
        .group_by(func.coalesce(ToastOrder.dining_option, "Unknown"))
    )).all()

    avg_s = float(overall.avg_s) if overall.avg_s is not None else None
    return {
        "data": {
            "avg_seconds": round(avg_s) if avg_s is not None else None,
            "target_seconds": target_seconds,
            "fastest_seconds": round(float(overall.min_s)) if overall.min_s is not None else None,
            "slowest_seconds": round(float(overall.max_s)) if overall.max_s is not None else None,
            "sample_size": overall.n,
            "by_channel": sorted(
                (
                    {
                        "channel": r.channel,
                        "avg_seconds": round(float(r.avg_s)) if r.avg_s is not None else None,
                        "order_count": r.n,
                    }
                    for r in by_channel_rows
                ),
                key=lambda c: c["avg_seconds"] or 0,
            ),
        },
        "errors": None,
    }


@router.get("/top-vendors", response_model=APIResponse[dict])
async def top_vendors(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    category: str | None = Query(None, description="Filter to one expense category"),
    location_id: uuid.UUID | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> dict:
    """Top vendors by spend, optionally within one category (e.g. Food Cost)."""
    start, end = _parse_range(date_from, date_to)

    conds = [
        Expense.tenant_id == user.tenant_id,
        Expense.expense_date >= start,
        Expense.expense_date <= end,
    ]
    if category:
        conds.append(Expense.category == category)
    if location_id is not None:
        conds.append(Expense.location_id == location_id)

    rows = (await db.execute(
        select(
            func.coalesce(Expense.vendor_name, "Unknown").label("vendor"),
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
            func.count(Expense.id).label("n"),
        )
        .where(and_(*conds))
        .group_by(func.coalesce(Expense.vendor_name, "Unknown"))
        .order_by(func.sum(Expense.amount).desc())
        .limit(limit)
    )).all()

    return {
        "data": {
            "vendors": [
                {"vendor": r.vendor, "total": round(float(r.total or 0), 2), "count": r.n}
                for r in rows
            ]
        },
        "errors": None,
    }


@router.get("/cash-forecast", response_model=APIResponse[dict])
async def cash_forecast(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    lookback_days: int = Query(30, ge=7, le=90),
    horizon_days: int = Query(7, ge=1, le=30),
) -> dict:
    """Run-rate projection of net cash flow over the next `horizon_days`.

    We don't store a live bank balance, so this projects FLOW (expected
    sales minus expense run-rate), not an absolute balance. Honest + derivable
    from synced Toast sales and booked expenses."""
    now = datetime.now(timezone.utc)
    lb_start = now - timedelta(days=lookback_days)

    sales_conds = [
        ToastOrder.tenant_id == user.tenant_id,
        ToastOrder.opened_at >= lb_start,
        ToastOrder.opened_at <= now,
        ToastOrder.is_void == False,  # noqa: E712
    ]
    if location_id is not None:
        sales_conds.append(ToastOrder.location_id == location_id)

    sales_total = (await db.execute(
        select(func.coalesce(func.sum(ToastOrder.net_amount), 0)).where(and_(*sales_conds))
    )).scalar_one()

    exp_conds = [
        Expense.tenant_id == user.tenant_id,
        Expense.expense_date >= lb_start,
        Expense.expense_date <= now,
    ]
    if location_id is not None:
        exp_conds.append(Expense.location_id == location_id)
    exp_total = (await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(*exp_conds))
    )).scalar_one()

    daily_sales = float(sales_total or 0) / lookback_days
    daily_exp = float(exp_total or 0) / lookback_days
    daily_net = daily_sales - daily_exp

    return {
        "data": {
            "horizon_days": horizon_days,
            "projected_net_flow": round(daily_net * horizon_days, 2),
            "avg_daily_sales": round(daily_sales, 2),
            "avg_daily_expense": round(daily_exp, 2),
            "lookback_days": lookback_days,
            "basis": "run_rate",
        },
        "errors": None,
    }
