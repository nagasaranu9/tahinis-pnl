"""P&L report and snapshot endpoints."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, select

from app.core.deps import CurrentUserDep, ManagerDep
from app.db.models.location import Location
from app.db.models.toast import ToastOrder, ToastOrderDiscount
from app.db.repositories.pnl_repo import PnLRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.pnl import (
    DailyBreakdownResponse,
    DailyRevenuePoint,
    PnLReportResponse,
    PnLSnapshotResponse,
)
from app.services.pnl.calculator import PnLCalculator
from app.services.pnl.export_service import generate_csv, generate_pdf

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/report", response_model=APIResponse[PnLReportResponse])
async def get_pnl_report(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Compute P&L on-the-fly for any date range."""
    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
        end_dt = datetime.fromisoformat(period_end).replace(hour=23, minute=59, second=59, tzinfo=UTC)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="period_start and period_end must be YYYY-MM-DD")

    calculator = PnLCalculator(db)
    report = await calculator.compute(
        tenant_id=user.tenant_id,
        period_start=start_dt,
        period_end=end_dt,
        location_id=location_id,
    )
    logger.info(
        "pnl_report_computed",
        tenant_id=str(user.tenant_id),
        period_start=period_start,
        period_end=period_end,
    )
    return {"data": report, "errors": None}


@router.get("/report/bank-basis")
async def get_bank_basis_pnl(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
) -> dict:
    """Bank-statement-basis P&L: revenue from deposits, before/after HST, partner split."""
    from fastapi.encoders import jsonable_encoder

    from app.services.pnl.bank_pnl import BankPnLCalculator

    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
        end_dt = datetime.fromisoformat(period_end).replace(hour=23, minute=59, second=59, tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=422, detail="period_start and period_end must be YYYY-MM-DD")

    report = await BankPnLCalculator(db).compute(user.tenant_id, start_dt, end_dt)
    return {"data": jsonable_encoder(report), "errors": None}


@router.get("/partners")
async def list_partners(user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    """Partner ownership shares for the tenant (bank-basis P&L split)."""
    from app.db.models.partner_share import PartnerShare

    rows = (await db.execute(
        select(PartnerShare).where(PartnerShare.tenant_id == user.tenant_id)
        .order_by(PartnerShare.sort_order, PartnerShare.name)
    )).scalars().all()
    return {"data": [
        {"name": p.name, "share_pct": str(p.share_pct)} for p in rows
    ], "errors": None}


@router.put("/partners")
async def set_partners(
    user: ManagerDep,
    db: AsyncSessionDep,
    partners: list[dict],
) -> dict:
    """Replace the tenant's partner shares. Body: [{name, share_pct}, ...]."""
    from sqlalchemy import delete

    from app.db.models.partner_share import PartnerShare

    total = Decimal("0")
    cleaned: list[tuple[str, Decimal]] = []
    for p in partners:
        name = str(p.get("name", "")).strip()
        if not name:
            raise HTTPException(status_code=422, detail="each partner needs a name")
        try:
            pct = Decimal(str(p.get("share_pct")))
        except Exception:
            raise HTTPException(status_code=422, detail=f"invalid share_pct for {name}")
        total += pct
        cleaned.append((name, pct))
    if cleaned and abs(total - Decimal("100")) > Decimal("0.01"):
        raise HTTPException(status_code=422, detail=f"shares must sum to 100 (got {total})")

    await db.execute(delete(PartnerShare).where(PartnerShare.tenant_id == user.tenant_id))
    for i, (name, pct) in enumerate(cleaned):
        db.add(PartnerShare(tenant_id=user.tenant_id, name=name, share_pct=pct, sort_order=i))
    await db.commit()
    return {"data": [{"name": n, "share_pct": str(p)} for n, p in cleaned], "errors": None}


@router.get("/daily-breakdown", response_model=APIResponse[DailyBreakdownResponse])
async def get_daily_breakdown(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Return per-day revenue totals from Toast orders for chart rendering."""
    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
        end_dt = datetime.fromisoformat(period_end).replace(hour=23, minute=59, second=59, tzinfo=UTC)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="period_start and period_end must be YYYY-MM-DD")

    start_str = period_start.replace("-", "")
    end_str = period_end.replace("-", "")
    conditions = [
        ToastOrder.tenant_id == user.tenant_id,
        ToastOrder.is_void.is_(False),
        ToastOrder.business_date >= start_str,
        ToastOrder.business_date <= end_str,
    ]
    if location_id:
        conditions.append(ToastOrder.location_id == location_id)

    stmt = (
        select(
            ToastOrder.business_date.label("day"),
            func.coalesce(
                func.sum(ToastOrder.net_amount + func.coalesce(ToastOrder.discount_amount, 0) + func.coalesce(ToastOrder.void_amount, 0)),
                0,
            ).label("gross_revenue"),
            func.coalesce(func.sum(ToastOrder.net_amount), 0).label("net_revenue"),
            func.coalesce(func.sum(ToastOrder.void_amount), 0).label("void_amount"),
            func.count(ToastOrder.id).label("order_count"),
        )
        .where(and_(*conditions))
        .group_by(ToastOrder.business_date)
        .order_by(ToastOrder.business_date)
    )

    result = await db.execute(stmt)
    rows = result.all()

    def _fmt_biz_date(d: str) -> str:
        # YYYYMMDD → YYYY-MM-DD
        return f"{d[:4]}-{d[4:6]}-{d[6:]}" if len(d) == 8 else d

    points = [
        DailyRevenuePoint(
            date=_fmt_biz_date(str(row.day)),
            gross_revenue=Decimal(str(row.gross_revenue)),
            net_revenue=Decimal(str(row.net_revenue)),
            void_amount=Decimal(str(row.void_amount)),
            order_count=row.order_count,
        )
        for row in rows
    ]

    return {
        "data": DailyBreakdownResponse(
            period_start=period_start,
            period_end=period_end,
            points=points,
        ),
        "errors": None,
    }


@router.get("/export")
async def export_pnl(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    format: str = Query("csv", description="csv or pdf"),
    basis: str = Query("toast", description="toast or bank"),
    location_id: uuid.UUID | None = Query(None),
) -> Response:
    """Export P&L report as CSV or PDF. Never modifies source records."""
    if format not in ("csv", "pdf"):
        raise HTTPException(status_code=422, detail="format must be 'csv' or 'pdf'")
    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=UTC)
        end_dt = datetime.fromisoformat(period_end).replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="period_start and period_end must be YYYY-MM-DD")

    # Bank-statement-basis export (CSV only for now — matches the P&L page's
    # Bank Statement view: deposits revenue, Before/After HST, partner split).
    if basis == "bank" and format == "csv":
        from app.services.pnl.bank_pnl import BankPnLCalculator
        from app.services.pnl.export_service import generate_bank_csv

        report_dict = await BankPnLCalculator(db).compute(user.tenant_id, start_dt, end_dt)
        loc_name = "All Locations"
        loc_tz: str | None = None
        if location_id:
            location = await db.get(Location, location_id)
            if location and location.tenant_id == user.tenant_id:
                loc_name, loc_tz = location.name, location.timezone
        content = generate_bank_csv(report_dict, location_name=loc_name, location_timezone=loc_tz)
        return Response(
            content=content, media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="tahinis_pnl_bank_{period_start}_{period_end}.csv"'},
        )

    calculator = PnLCalculator(db)
    report = await calculator.compute(
        tenant_id=user.tenant_id,
        period_start=start_dt,
        period_end=end_dt,
        location_id=location_id,
    )

    location_name = "All Locations"
    location_timezone: str | None = None
    if location_id:
        location = await db.get(Location, location_id)
        if location is None or location.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Location not found")
        user.require_location_access(location.id)
        location_name = location.name
        location_timezone = location.timezone

    filename = f"tahinis_pnl_{period_start}_{period_end}"

    if format == "csv":
        content = generate_csv(report, location_name=location_name, location_timezone=location_timezone)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    content = generate_pdf(report, location_name=location_name, location_timezone=location_timezone)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


@router.get("/discount-breakdown", response_model=APIResponse[dict])
async def discount_breakdown(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Discounts for the period grouped by promo name.

    Discounts run ~13% of gross revenue, but the P&L only shows the total —
    which hides whether that's a delivery-marketplace promo (a channel cost of
    doing business) or staff comps (a controllable leak). Grouping by Toast's
    discount name separates them.
    """
    try:
        start_bd = datetime.fromisoformat(period_start).strftime("%Y%m%d")
        end_bd = datetime.fromisoformat(period_end).strftime("%Y%m%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="period_start and period_end must be YYYY-MM-DD"
        ) from exc

    conds = [
        ToastOrderDiscount.tenant_id == user.tenant_id,
        ToastOrderDiscount.business_date >= start_bd,
        ToastOrderDiscount.business_date <= end_bd,
    ]
    if location_id:
        conds.append(ToastOrderDiscount.location_id == location_id)

    rows = (await db.execute(
        select(
            ToastOrderDiscount.name,
            ToastOrderDiscount.scope,
            func.sum(ToastOrderDiscount.amount).label("total"),
            func.count(ToastOrderDiscount.id).label("count"),
        )
        .where(and_(*conds))
        .group_by(ToastOrderDiscount.name, ToastOrderDiscount.scope)
        .order_by(func.sum(ToastOrderDiscount.amount).desc())
    )).all()

    total = sum((r.total for r in rows), Decimal("0"))
    return {
        "data": {
            "total": total,
            "currency_code": "CAD",
            "discounts": [
                {
                    "name": r.name,
                    "scope": r.scope,
                    "total": r.total,
                    "count": r.count,
                    "pct_of_discounts": (
                        (r.total / total * 100).quantize(Decimal("0.1")) if total else None
                    ),
                }
                for r in rows
            ],
        },
        "errors": None,
    }


@router.post("/discount-backfill", response_model=APIResponse[dict])
async def discount_backfill(
    user: ManagerDep,
    db: AsyncSessionDep,
    limit: int = Query(20000, ge=1, le=100000),
) -> dict:
    """Populate named discounts from already-synced orders' stored raw_data.

    Discount names were always present in Toast's payload but discarded before
    this table existed; the raw order JSON is retained, so history can be
    recovered without re-hitting the Toast API (and its rate limits).
    """
    import json

    from app.db.repositories.toast_repo import ToastRepository
    from app.services.toast.sync_service import iter_applied_discounts

    repo = ToastRepository(db)
    rows = (await db.execute(
        select(ToastOrder.id, ToastOrder.location_id, ToastOrder.business_date, ToastOrder.raw_data)
        .where(
            ToastOrder.tenant_id == user.tenant_id,
            ToastOrder.raw_data.isnot(None),
            ToastOrder.discount_amount.isnot(None),
        )
        .limit(limit)
    )).all()

    orders_scanned = 0
    discounts_written = 0
    for order_id, loc_id, business_date, raw_json in rows:
        orders_scanned += 1
        try:
            raw = json.loads(raw_json)
        except (ValueError, TypeError):
            continue
        for disc in iter_applied_discounts(raw):
            await repo.upsert_order_discount({
                "id": uuid.uuid4(),
                "tenant_id": user.tenant_id,
                "order_id": order_id,
                "location_id": loc_id,
                "toast_guid": disc["guid"],
                "business_date": business_date,
                "name": disc["name"],
                "discount_type": disc["discount_type"],
                "scope": disc["scope"],
                "amount": disc["amount"],
            })
            discounts_written += 1
        # Commit per batch of orders to keep the transaction from growing
        # unbounded across a multi-year backfill.
        if orders_scanned % 500 == 0:
            await db.commit()
    await db.commit()

    logger.info(
        "toast_discount_backfill_complete",
        tenant_id=str(user.tenant_id),
        orders_scanned=orders_scanned,
        discounts_written=discounts_written,
    )
    return {
        "data": {"orders_scanned": orders_scanned, "discounts_written": discounts_written},
        "errors": None,
    }


@router.get("/trend", response_model=APIResponse[dict])
async def pnl_trend(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    months: int = Query(6, ge=2, le=24),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Month-by-month P&L series for sparklines.

    Computed through PnLCalculator per month rather than read from snapshots:
    snapshots are written by a monthly job and would silently serve figures
    predating any calculation fix (dedup, interest split), so a trend built on
    them can disagree with the report shown right above it.
    """
    import asyncio
    from calendar import monthrange

    from app.db.session import AsyncSessionLocal

    today = datetime.now(UTC)

    # Walk back `months` calendar months, oldest first.
    year, month = today.year, today.month
    periods: list[tuple[int, int]] = []
    for _ in range(months):
        periods.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    periods.reverse()

    async def _month(yr: int, mo: int) -> dict:
        start = datetime(yr, mo, 1, tzinfo=UTC)
        end = datetime(yr, mo, monthrange(yr, mo)[1], 23, 59, 59, tzinfo=UTC)
        # Each month gets its own session: a single AsyncSession can't be shared
        # across concurrent tasks, and running the months sequentially on the
        # request's session made this endpoint several times slower than the
        # report it sits next to.
        async with AsyncSessionLocal() as session:
            report = await PnLCalculator(session).compute(
                tenant_id=user.tenant_id,
                period_start=start,
                period_end=end,
                location_id=location_id,
            )
        li = report.line_items
        return {
            "period_label": f"{yr}-{mo:02d}",
            "period_start": start.date().isoformat(),
            "net_revenue": li.net_revenue,
            "cogs": li.cogs,
            "cogs_pct": li.cogs_pct,
            "labor_cost": li.labor_cost,
            "labor_pct": li.labor_pct,
            "prime_cost_pct": li.prime_cost_pct,
            "ebitda": li.ebitda,
            "net_profit": li.net_profit,
            "net_profit_pct": li.net_profit_pct,
        }

    points = await asyncio.gather(*(_month(yr, mo) for yr, mo in periods))
    return {"data": {"months": months, "points": list(points)}, "errors": None}


@router.get("/snapshots", response_model=PaginatedResponse[PnLSnapshotResponse])
async def list_pnl_snapshots(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(24, ge=1, le=120),
) -> dict:
    repo = PnLRepository(db)
    rows, total = await repo.list_snapshots(
        tenant_id=user.tenant_id,
        location_id=location_id,
        page=page,
        limit=limit,
    )
    return {
        "data": [PnLSnapshotResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }
