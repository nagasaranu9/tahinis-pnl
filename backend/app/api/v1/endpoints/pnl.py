"""P&L report and snapshot endpoints."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, func, select

from app.core.deps import CurrentUserDep
from app.db.models.toast import ToastOrder
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
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(period_end).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
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
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(period_end).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
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
    location_id: uuid.UUID | None = Query(None),
) -> Response:
    """Export P&L report as CSV or PDF. Never modifies source records."""
    if format not in ("csv", "pdf"):
        raise HTTPException(status_code=422, detail="format must be 'csv' or 'pdf'")
    try:
        start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
        end_dt = datetime.fromisoformat(period_end).replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="period_start and period_end must be YYYY-MM-DD")

    calculator = PnLCalculator(db)
    report = await calculator.compute(
        tenant_id=user.tenant_id,
        period_start=start_dt,
        period_end=end_dt,
        location_id=location_id,
    )

    filename = f"tahinis_pnl_{period_start}_{period_end}"

    if format == "csv":
        content = generate_csv(report)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )

    content = generate_pdf(report)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


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
