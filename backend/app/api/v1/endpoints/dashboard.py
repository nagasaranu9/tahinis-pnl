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
from sqlalchemy import and_, func, or_, select

from app.core.config import settings
from app.core.deps import CurrentUserDep
from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.external_platform import PipeboardCampaign, PipeboardDailyMetric
from app.db.models.google_reviews import GoogleReview
from app.db.models.reconciliation import ReconciliationFlag
from app.db.models.toast import ToastOrder, ToastOrderItem
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
    # Select by Toast's native business_date (YYYYMMDD string, 4am→3:59am day
    # boundary) — same basis as the P&L calculator. opened_at is a tz-aware
    # timestamp that can be null or offset, which silently dropped every row.
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")
    conds = [
        ToastOrder.tenant_id == user.tenant_id,
        ToastOrder.business_date >= start_str,
        ToastOrder.business_date <= end_str,
        ToastOrder.is_void == False,  # noqa: E712
    ]
    if location_id is not None:
        conds.append(ToastOrder.location_id == location_id)
    return conds


# Map raw Toast order_source / dining_option strings to a friendly channel label.
# Third-party delivery arrives via order_source (sourceType); in-house orders use
# dining_option (TakeOut / Dine In). We prefer a recognised delivery source, else
# fall back to the dining option.
_DELIVERY_SOURCE_LABELS = {
    "uber": "Uber Eats",
    "ubereats": "Uber Eats",
    "skip": "Skip",
    "skipthedishes": "Skip",
    "doordash": "DoorDash",
    "tacit": "Tacit App",
    "grubhub": "Grubhub",
}


def _clean_dining(name: str) -> str:
    """Strip Toast noise: leading '**' (third-party tag) and store-number
    prefix like '1941 - '."""
    n = name.strip().lstrip("*").strip()
    # Drop a leading "<digits> - " store prefix.
    if " - " in n:
        head, rest = n.split(" - ", 1)
        if head.strip().isdigit():
            n = rest.strip()
    return n


def _channel_label(dining_option: str | None, order_source: str | None) -> str:
    # Channel lives in dining_option (Toast: Dine In / Take Out / **Uber /
    # **Skip / **Doordash / **Tacit PU). order_source is a secondary signal.
    haystack = f"{dining_option or ''} {order_source or ''}".lower()
    for key, label in _DELIVERY_SOURCE_LABELS.items():
        if key in haystack:
            return label
    if dining_option and dining_option.strip():
        return _clean_dining(dining_option)
    if order_source and order_source.strip():
        return order_source.strip()
    return "Unknown"


@router.get("/channel-mix", response_model=APIResponse[dict])
async def channel_mix(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Revenue split by channel — merges Toast dining_option (TakeOut / Dine-in)
    with order_source (Uber Eats / Skip / DoorDash / Tacit)."""
    start, end = _parse_range(date_from, date_to)

    rows = (await db.execute(
        select(
            ToastOrder.dining_option,
            ToastOrder.order_source,
            func.coalesce(func.sum(ToastOrder.net_amount), 0).label("revenue"),
            func.count(ToastOrder.id).label("order_count"),
        )
        .where(and_(*_toast_filters(user, location_id, start, end)))
        .group_by(ToastOrder.dining_option, ToastOrder.order_source)
    )).all()

    agg: dict[str, dict] = {}
    for r in rows:
        label = _channel_label(r.dining_option, r.order_source)
        bucket = agg.setdefault(label, {"channel": label, "revenue": 0.0, "order_count": 0})
        bucket["revenue"] += float(r.revenue or 0)
        bucket["order_count"] += r.order_count

    total = sum(b["revenue"] for b in agg.values()) or 0.0
    channels = sorted(
        (
            {
                "channel": b["channel"],
                "revenue": round(b["revenue"], 2),
                "order_count": b["order_count"],
                "pct": round(b["revenue"] / total * 100, 1) if total > 0 else 0.0,
            }
            for b in agg.values()
        ),
        key=lambda c: c["revenue"],
        reverse=True,
    )
    return {"data": {"total_revenue": round(total, 2), "channels": channels}, "errors": None}


@router.get("/discounts-voids", response_model=APIResponse[dict])
async def discounts_voids(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Discounts + voids for the period and their share of gross sales."""
    start, end = _parse_range(date_from, date_to)
    row = (await db.execute(
        select(
            func.coalesce(func.sum(ToastOrder.discount_amount), 0).label("discounts"),
            func.coalesce(func.sum(ToastOrder.void_amount), 0).label("voids"),
            func.coalesce(func.sum(ToastOrder.net_amount), 0).label("net"),
        ).where(and_(*_toast_filters(user, location_id, start, end)))
    )).one()
    discounts = float(row.discounts or 0)
    voids = float(row.voids or 0)
    net = float(row.net or 0)
    gross = net + discounts + voids
    return {
        "data": {
            "discounts": round(discounts, 2),
            "voids": round(voids, 2),
            "total_loss": round(discounts + voids, 2),
            "pct_of_sales": round((discounts + voids) / gross * 100, 1) if gross > 0 else 0.0,
        },
        "errors": None,
    }


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
        .group_by(ToastOrder.dining_option)
    )).all()

    # Peak hour: hour-of-day with the highest average wait.
    hour = func.extract("hour", ToastOrder.opened_at)
    peak_rows = (await db.execute(
        select(hour.label("hr"), func.avg(duration).label("avg_s"), func.count(ToastOrder.id).label("n"))
        .where(and_(*base_conds))
        .group_by(hour)
    )).all()
    peak = max(
        (r for r in peak_rows if r.n >= 3),
        key=lambda r: float(r.avg_s or 0),
        default=None,
    )

    avg_s = float(overall.avg_s) if overall.avg_s is not None else None
    return {
        "data": {
            "avg_seconds": round(avg_s) if avg_s is not None else None,
            "target_seconds": target_seconds,
            "fastest_seconds": round(float(overall.min_s)) if overall.min_s is not None else None,
            "slowest_seconds": round(float(overall.max_s)) if overall.max_s is not None else None,
            "sample_size": overall.n,
            "peak_hour": int(peak.hr) if peak is not None else None,
            "peak_hour_seconds": round(float(peak.avg_s)) if peak is not None else None,
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


@router.get("/product-mix", response_model=APIResponse[dict])
async def product_mix(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
    limit: int = Query(6, ge=1, le=50),
) -> dict:
    """Top-selling menu items (Toast) by quantity over a range.

    Aggregates ToastOrderItem rows for non-void orders/items, grouped by item
    name. Shows quantity sold and average unit price per item."""
    start, end = _parse_range(date_from, date_to)
    conds = _toast_filters(user, location_id, start, end) + [
        ToastOrderItem.is_void == False,  # noqa: E712
    ]

    qty = func.coalesce(func.sum(ToastOrderItem.quantity), 0)
    revenue = func.coalesce(func.sum(ToastOrderItem.pre_discount_price), 0)
    # Fallback: if unit_price is NULL, calculate from pre_discount_price / quantity
    unit_price_calc = func.case(
        (ToastOrderItem.unit_price.isnot(None), ToastOrderItem.unit_price),
        else_=func.nullif(ToastOrderItem.pre_discount_price / func.nullif(ToastOrderItem.quantity, 0), None),
    )
    unit_price_avg = func.coalesce(func.avg(unit_price_calc), 0)

    rows = (await db.execute(
        select(
            ToastOrderItem.name.label("name"),
            qty.label("qty"),
            revenue.label("revenue"),
            unit_price_avg.label("unit_price_avg"),
        )
        .join(ToastOrder, ToastOrderItem.order_id == ToastOrder.id)
        .where(and_(*conds))
        .group_by(ToastOrderItem.name)
        .order_by(qty.desc())
        .limit(limit)
    )).all()

    grand = (await db.execute(
        select(revenue)
        .join(ToastOrder, ToastOrderItem.order_id == ToastOrder.id)
        .where(and_(*conds))
    )).scalar() or 0
    grand = float(grand)

    items = [
        {
            "name": r.name,
            "quantity": float(r.qty or 0),
            "unit_price": round(float(r.unit_price_avg or 0), 2),
            "share": round(float(r.revenue or 0) / grand, 4) if grand > 0 else 0.0,
        }
        for r in rows
    ]
    return {"data": {"items": items, "total_revenue": round(grand, 2)}, "errors": None}


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
        # Match the P&L calculator: include tenant-wide expenses (NULL location),
        # e.g. manually-uploaded Alex invoices with no location attached.
        conds.append(or_(Expense.location_id == location_id, Expense.location_id.is_(None)))

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

    # Grand total across ALL vendors in scope (for share-of-spend %).
    grand_total = float((await db.execute(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(and_(*conds))
    )).scalar_one() or 0)

    return {
        "data": {
            "grand_total": round(grand_total, 2),
            "vendors": [
                {
                    "vendor": r.vendor,
                    "total": round(float(r.total or 0), 2),
                    "count": r.n,
                    "pct": round(float(r.total or 0) / grand_total * 100, 1) if grand_total > 0 else 0.0,
                }
                for r in rows
            ],
        },
        "errors": None,
    }


@router.get("/top-line-items", response_model=APIResponse[dict])
async def top_line_items(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    vendor: str = Query("alex food", description="Vendor name substring"),
    location_id: uuid.UUID | None = Query(None),
    limit: int = Query(5, ge=1, le=20),
) -> dict:
    """Top product line items by spend for one vendor (e.g. Alex Food).

    Reads OCR'd invoice/receipt line items (ExtractedLineItem) for documents
    whose vendor_name matches `vendor`, grouped by product description. Bank
    statements have no line items, so this only populates once that vendor's
    invoices are OCR'd."""
    from app.db.models.document import ExtractedLineItem

    start, end = _parse_range(date_from, date_to)

    conds = [
        ExtractedLineItem.tenant_id == user.tenant_id,
        Document.vendor_name.ilike(f"%{vendor}%"),
        Document.document_date >= start,
        Document.document_date <= end,
        # "Balance Forward" is a statement carry-over line, not a product.
        ~ExtractedLineItem.description.ilike("%balance forward%"),
    ]
    if location_id is not None:
        # Include tenant-wide documents (NULL location) — manual uploads often
        # have no location attached, same basis as the P&L calculator.
        conds.append(or_(Document.location_id == location_id, Document.location_id.is_(None)))

    # Group by an alphanumeric-only key so the same product spelled with
    # different punctuation/spacing/truncation ("Legs BL SL ROASTER Chicken,
    # 25kg/box" vs "... - 25kg/bo") collapses into one item, summed across all
    # invoices in the period.
    desc_key = func.regexp_replace(
        func.lower(ExtractedLineItem.description), r"[^a-z0-9]+", "", "g"
    )
    rows = (await db.execute(
        select(
            func.min(ExtractedLineItem.description).label("description"),
            func.coalesce(func.sum(ExtractedLineItem.amount), 0).label("total"),
            func.coalesce(func.sum(ExtractedLineItem.quantity), 0).label("qty"),
            func.count(ExtractedLineItem.id).label("n"),
        )
        .join(Document, ExtractedLineItem.document_id == Document.id)
        .where(and_(*conds))
        .group_by(desc_key)
        .order_by(func.sum(ExtractedLineItem.amount).desc())
        .limit(limit)
    )).all()

    grand_total = float((await db.execute(
        select(func.coalesce(func.sum(ExtractedLineItem.amount), 0))
        .join(Document, ExtractedLineItem.document_id == Document.id)
        .where(and_(*conds))
    )).scalar_one() or 0)

    return {
        "data": {
            "vendor": vendor,
            "grand_total": round(grand_total, 2),
            "items": [
                {
                    "description": r.description,
                    "total": round(float(r.total or 0), 2),
                    "quantity": round(float(r.qty or 0), 2),
                    "count": r.n,
                    "pct": round(float(r.total or 0) / grand_total * 100, 1) if grand_total > 0 else 0.0,
                }
                for r in rows
            ],
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
        ToastOrder.business_date >= lb_start.strftime("%Y%m%d"),
        ToastOrder.business_date <= now.strftime("%Y%m%d"),
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


@router.get("/invoice-status", response_model=APIResponse[dict])
async def invoice_status(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Invoice reconciliation coverage: matched / pending / unmatched / duplicate.

    Documents in range are the denominator; unresolved invoice-related flags are
    the gaps. Coverage = matched / imported."""
    start, end = _parse_range(date_from, date_to)

    doc_conds = [
        Document.tenant_id == user.tenant_id,
        Document.created_at >= start,
        Document.created_at <= end,
        Document.document_type.in_(("invoice", "receipt")),
    ]
    if location_id is not None:
        doc_conds.append(Document.location_id == location_id)
    imported = int((await db.execute(
        select(func.count(Document.id)).where(and_(*doc_conds))
    )).scalar_one() or 0)

    # Unresolved invoice-related flags grouped by type.
    flag_conds = [
        ReconciliationFlag.tenant_id == user.tenant_id,
        ReconciliationFlag.resolved_at.is_(None),
        ReconciliationFlag.flag_type.in_(
            ("missing_invoice", "duplicate_invoice", "unmatched_sale")
        ),
        ReconciliationFlag.created_at >= start,
        ReconciliationFlag.created_at <= end,
    ]
    flag_rows = (await db.execute(
        select(ReconciliationFlag.flag_type, func.count(ReconciliationFlag.id))
        .where(and_(*flag_conds))
        .group_by(ReconciliationFlag.flag_type)
    )).all()
    by_type = {ft: n for ft, n in flag_rows}

    duplicate = by_type.get("duplicate_invoice", 0)
    unmatched = by_type.get("missing_invoice", 0) + by_type.get("unmatched_sale", 0)
    pending = unmatched + duplicate
    matched = max(imported - pending, 0)
    coverage = round(matched / imported * 100, 1) if imported > 0 else None

    return {
        "data": {
            "imported": imported,
            "matched": matched,
            "pending": pending,
            "unmatched": unmatched,
            "duplicate": duplicate,
            "coverage_pct": coverage,
        },
        "errors": None,
    }


@router.get("/ads-detail", response_model=APIResponse[dict])
async def ads_detail(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    platform: str = Query("google_ads", description="google_ads / meta_ads / tiktok_ads"),
) -> dict:
    """Full ad metrics for one platform over a range + daily spend series."""
    df, dt = date_from, date_to

    base = (
        select(PipeboardDailyMetric)
        .join(PipeboardCampaign, PipeboardDailyMetric.campaign_id == PipeboardCampaign.id)
        .where(
            PipeboardCampaign.tenant_id == user.tenant_id,
            PipeboardCampaign.pipeboard_platform == platform,
            PipeboardDailyMetric.metric_date >= df,
            PipeboardDailyMetric.metric_date <= dt,
        )
    )

    totals = (await db.execute(
        select(
            func.coalesce(func.sum(PipeboardDailyMetric.spend), 0).label("spend"),
            func.coalesce(func.sum(PipeboardDailyMetric.impressions), 0).label("impr"),
            func.coalesce(func.sum(PipeboardDailyMetric.clicks), 0).label("clicks"),
            func.coalesce(func.sum(PipeboardDailyMetric.conversions), 0).label("conv"),
            func.coalesce(func.sum(PipeboardDailyMetric.conversion_value), 0).label("conv_val"),
        )
        .join(PipeboardCampaign, PipeboardDailyMetric.campaign_id == PipeboardCampaign.id)
        .where(
            PipeboardCampaign.tenant_id == user.tenant_id,
            PipeboardCampaign.pipeboard_platform == platform,
            PipeboardDailyMetric.metric_date >= df,
            PipeboardDailyMetric.metric_date <= dt,
        )
    )).one()

    spend = float(totals.spend or 0)
    impr = int(totals.impr or 0)
    clicks = int(totals.clicks or 0)
    conv = float(totals.conv or 0)
    conv_val = float(totals.conv_val or 0)

    daily_rows = (await db.execute(
        select(
            PipeboardDailyMetric.metric_date,
            func.coalesce(func.sum(PipeboardDailyMetric.spend), 0).label("spend"),
        )
        .join(PipeboardCampaign, PipeboardDailyMetric.campaign_id == PipeboardCampaign.id)
        .where(
            PipeboardCampaign.tenant_id == user.tenant_id,
            PipeboardCampaign.pipeboard_platform == platform,
            PipeboardDailyMetric.metric_date >= df,
            PipeboardDailyMetric.metric_date <= dt,
        )
        .group_by(PipeboardDailyMetric.metric_date)
        .order_by(PipeboardDailyMetric.metric_date)
    )).all()

    return {
        "data": {
            "platform": platform,
            "spend": round(spend, 2),
            "impressions": impr,
            "clicks": clicks,
            "conversions": round(conv, 1),
            "ctr": round(clicks / impr * 100, 2) if impr > 0 else 0.0,
            "cpc": round(spend / clicks, 2) if clicks > 0 else 0.0,
            "cost_per_conversion": round(spend / conv, 2) if conv > 0 else None,
            "roas": round(conv_val / spend, 2) if spend > 0 else None,
            "daily_spend": [
                {"date": r.metric_date, "spend": round(float(r.spend or 0), 2)} for r in daily_rows
            ],
        },
        "errors": None,
    }


@router.get("/ads-campaigns", response_model=APIResponse[dict])
async def ads_campaigns(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    platform: str = Query("google_ads", description="google_ads / meta_ads / tiktok_ads"),
) -> dict:
    """Per-campaign performance for one platform over a range, plus account totals.

    Powers the Marketing → Google Ads campaign table + summary cards."""
    df, dt = date_from, date_to

    rows = (await db.execute(
        select(
            PipeboardCampaign.pipeboard_campaign_id.label("cid"),
            PipeboardCampaign.name.label("name"),
            PipeboardCampaign.status.label("status"),
            PipeboardCampaign.campaign_type.label("type"),
            PipeboardCampaign.daily_budget_limit.label("daily_budget"),
            func.coalesce(func.sum(PipeboardDailyMetric.spend), 0).label("spend"),
            func.coalesce(func.sum(PipeboardDailyMetric.impressions), 0).label("impr"),
            func.coalesce(func.sum(PipeboardDailyMetric.clicks), 0).label("clicks"),
            func.coalesce(func.sum(PipeboardDailyMetric.conversions), 0).label("conv"),
            func.coalesce(func.sum(PipeboardDailyMetric.conversion_value), 0).label("conv_val"),
        )
        .outerjoin(
            PipeboardDailyMetric,
            and_(
                PipeboardDailyMetric.campaign_id == PipeboardCampaign.id,
                PipeboardDailyMetric.metric_date >= df,
                PipeboardDailyMetric.metric_date <= dt,
            ),
        )
        .where(
            PipeboardCampaign.tenant_id == user.tenant_id,
            PipeboardCampaign.pipeboard_platform == platform,
        )
        .group_by(
            PipeboardCampaign.id,
            PipeboardCampaign.pipeboard_campaign_id,
            PipeboardCampaign.name,
            PipeboardCampaign.status,
            PipeboardCampaign.campaign_type,
            PipeboardCampaign.daily_budget_limit,
        )
        .order_by(func.sum(PipeboardDailyMetric.spend).desc().nullslast())
    )).all()

    campaigns = []
    t_spend = t_impr = t_clicks = 0.0
    t_conv = t_conv_val = 0.0
    for r in rows:
        spend = float(r.spend or 0)
        impr = int(r.impr or 0)
        clicks = int(r.clicks or 0)
        conv = float(r.conv or 0)
        conv_val = float(r.conv_val or 0)
        t_spend += spend
        t_impr += impr
        t_clicks += clicks
        t_conv += conv
        t_conv_val += conv_val
        campaigns.append({
            "campaign_id": r.cid,
            "name": r.name,
            "status": r.status,
            "type": r.type,
            "daily_budget": round(float(r.daily_budget), 2) if r.daily_budget is not None else None,
            "spend": round(spend, 2),
            "impressions": impr,
            "clicks": clicks,
            "conversions": round(conv, 1),
            "conversion_value": round(conv_val, 2),
            "ctr": round(clicks / impr * 100, 2) if impr > 0 else 0.0,
            "cpc": round(spend / clicks, 2) if clicks > 0 else 0.0,
            "roas": round(conv_val / spend, 2) if spend > 0 else None,
        })

    return {
        "data": {
            "platform": platform,
            "totals": {
                "spend": round(t_spend, 2),
                "impressions": int(t_impr),
                "clicks": int(t_clicks),
                "conversions": round(t_conv, 1),
                "ctr": round(t_clicks / t_impr * 100, 2) if t_impr > 0 else 0.0,
                "cpc": round(t_spend / t_clicks, 2) if t_clicks > 0 else 0.0,
                "roas": round(t_conv_val / t_spend, 2) if t_spend > 0 else None,
            },
            "campaigns": campaigns,
        },
        "errors": None,
    }


@router.get("/reviews-detail", response_model=APIResponse[dict])
async def reviews_detail(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Review counts, star breakdown, this-month activity, and response rate."""
    async def _fetch(loc: uuid.UUID | None):
        conds = [GoogleReview.tenant_id == user.tenant_id]
        if loc is not None:
            conds.append(GoogleReview.location_id == loc)
        return (await db.execute(
            select(GoogleReview.rating, GoogleReview.published_at, GoogleReview.reply_comment)
            .where(and_(*conds))
        )).all()

    rows = await _fetch(location_id)
    # Reviews are stored under the GBP config's location, which can differ from
    # the sidebar-selected location. If the scoped query is empty, fall back to
    # tenant-wide so the dashboard tile isn't stuck on "Connect" while the
    # Reviews tab clearly has data.
    snapshot_loc = location_id
    if not rows and location_id is not None:
        rows = await _fetch(None)
        snapshot_loc = None

    total = len(rows)
    stars = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    rating_sum = 0
    rating_n = 0
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = 0
    month_rating_sum = 0
    month_rating_n = 0
    replied = 0
    unanswered = 0

    for r in rows:
        if r.rating in stars:
            stars[r.rating] += 1
            rating_sum += r.rating
            rating_n += 1
        if r.reply_comment:
            replied += 1
        else:
            unanswered += 1
        if r.published_at and r.published_at >= month_start:
            new_this_month += 1
            if r.rating:
                month_rating_sum += r.rating
                month_rating_n += 1

    # Prefer the true aggregate rating + total from the latest snapshot (Places
    # API returns the real 4.8 / 1995, not the 5-review sample average).
    avg_rating = round(rating_sum / rating_n, 1) if rating_n else None
    total_reviews = total
    from app.db.repositories.reviews_repo import ReviewsRepository
    snap = await ReviewsRepository(db).get_latest_snapshot(user.tenant_id, snapshot_loc)
    if snap is not None and snap.review_count_total:
        if snap.rating_average is not None:
            avg_rating = round(float(snap.rating_average), 1)
        total_reviews = snap.review_count_total

    return {
        "data": {
            "average_rating": avg_rating,
            "total_reviews": total_reviews,
            "stars": {f"{k}_star": v for k, v in stars.items()},
            "new_this_month": new_this_month,
            "month_avg_rating": round(month_rating_sum / month_rating_n, 1) if month_rating_n else None,
            "response_rate_pct": round(replied / total * 100, 1) if total else None,
            "unanswered": unanswered,
        },
        "errors": None,
    }


@router.get("/profit-suggestions", response_model=APIResponse[dict])
async def profit_suggestions(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    date_from: str = Query(..., description="YYYY-MM-DD"),
    date_to: str = Query(..., description="YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """AI suggestions to improve NET profit for the period.

    Runs the real P&L, hands the numbers to Claude, returns 3-5 concrete,
    restaurant-specific actions ranked by estimated monthly $ impact. On-demand
    + synchronous (no async queue) so it's reliable; client should cache."""
    start, end = _parse_range(date_from, date_to)

    from app.services.pnl.calculator import PnLCalculator
    report = await PnLCalculator(db).compute(user.tenant_id, start, end, location_id)
    li = report.line_items

    if not settings.ANTHROPIC_API_KEY:
        return {"data": {"available": False, "reason": "no_api_key"}, "errors": None}

    def _f(v) -> float:
        return float(v) if v is not None else 0.0

    metrics = {
        "net_revenue": _f(li.net_revenue),
        "cogs": _f(li.cogs),
        "cogs_pct": _f(li.cogs_pct),
        "labor_cost": _f(li.labor_cost),
        "labor_pct": _f(li.labor_pct),
        "prime_cost_pct": _f(li.prime_cost_pct),
        "operating_expenses": _f(li.operating_expenses),
        "ebitda": _f(li.ebitda),
        "net_profit": _f(li.net_profit),
        "net_profit_pct": _f(li.net_profit_pct),
    }
    breakdown = [
        {"category": b.category, "total": _f(b.total)}
        for b in (report.expense_breakdown or [])
    ]

    import json as _json

    import anthropic

    prompt = (
        "You are a restaurant CFO. Given this P&L for the period, suggest 3-5 "
        "concrete actions to improve NET PROFIT. Each must be specific and "
        "restaurant-relevant (food cost %, labor scheduling, supplier "
        "renegotiation, menu pricing/mix, waste, marketing ROAS, opex). "
        "Benchmarks: food cost target ~30-34% of net sales, labor ~28-32%, "
        "prime cost <60%.\n\n"
        f"Period: {date_from} to {date_to}\n"
        f"Metrics: {_json.dumps(metrics)}\n"
        f"Expense categories: {_json.dumps(breakdown)}\n\n"
        "Respond ONLY with JSON:\n"
        '{"headline": "<one-sentence overall read>", "suggestions": ['
        '{"title": "<short action>", "detail": "<1-2 sentence how>", '
        '"impact_monthly": <estimated CAD $/month improvement, int>, '
        '"priority": "high|medium|low"}]}\n'
        "Sort suggestions by impact_monthly desc. JSON only:"
    )
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = _json.loads(raw)
        data["available"] = True
        data["metrics"] = metrics
        return {"data": data, "errors": None}
    except Exception as exc:
        logger.warning("profit_suggestions_failed", error=str(exc))
        return {"data": {"available": False, "reason": "analysis_failed"}, "errors": None}


@router.get("/reviews-sentiment", response_model=APIResponse[dict])
async def reviews_sentiment(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    sample: int = Query(60, ge=10, le=150, description="Most recent N reviews to analyse"),
) -> dict:
    """Claude pass over recent review text → positive sentiment % + top complaint
    and top praise theme. On-demand; cache on the client (slow + costs credits)."""
    conds = [GoogleReview.tenant_id == user.tenant_id, GoogleReview.comment.isnot(None)]
    if location_id is not None:
        conds.append(GoogleReview.location_id == location_id)

    rows = (await db.execute(
        select(GoogleReview.rating, GoogleReview.comment)
        .where(and_(*conds))
        .order_by(GoogleReview.published_at.desc().nullslast())
        .limit(sample)
    )).all()

    if not rows or not settings.ANTHROPIC_API_KEY:
        return {
            "data": {"available": False, "reason": "no_reviews_or_key"},
            "errors": None,
        }

    import json as _json

    import anthropic

    snippets = "\n".join(
        f"- ({r.rating}★) {(r.comment or '')[:300]}" for r in rows if r.comment
    )[:9000]
    prompt = (
        "Analyse these restaurant Google reviews. Respond ONLY with JSON:\n"
        '{"positive_pct": <0-100 int>, "top_complaint": "<short phrase>", '
        '"top_complaint_count": <int>, "top_praise": "<short phrase>", '
        '"top_praise_count": <int>}\n'
        "positive_pct = share of reviews with positive overall sentiment.\n\n"
        f"Reviews:\n{snippets}\n\nJSON only:"
    )
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        data = _json.loads(raw)
        data["available"] = True
        data["sample_size"] = len(rows)
        return {"data": data, "errors": None}
    except Exception as exc:
        logger.warning("reviews_sentiment_failed", error=str(exc))
        return {"data": {"available": False, "reason": "analysis_failed"}, "errors": None}
