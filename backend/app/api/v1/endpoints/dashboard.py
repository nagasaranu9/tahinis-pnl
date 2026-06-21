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

from app.core.config import settings
from app.core.deps import CurrentUserDep
from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.external_platform import PipeboardCampaign, PipeboardDailyMetric
from app.db.models.google_reviews import GoogleReview
from app.db.models.reconciliation import ReconciliationFlag
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


def _channel_label(dining_option: str | None, order_source: str | None) -> str:
    src = (order_source or "").strip().lower()
    for key, label in _DELIVERY_SOURCE_LABELS.items():
        if key in src:
            return label
    if dining_option and dining_option.strip():
        return dining_option.strip()
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
        .group_by(func.coalesce(ToastOrder.dining_option, "Unknown"))
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


@router.get("/reviews-detail", response_model=APIResponse[dict])
async def reviews_detail(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Review counts, star breakdown, this-month activity, and response rate."""
    conds = [GoogleReview.tenant_id == user.tenant_id]
    if location_id is not None:
        conds.append(GoogleReview.location_id == location_id)

    rows = (await db.execute(
        select(GoogleReview.rating, GoogleReview.published_at, GoogleReview.reply_comment)
        .where(and_(*conds))
    )).all()

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

    return {
        "data": {
            "average_rating": round(rating_sum / rating_n, 1) if rating_n else None,
            "total_reviews": total,
            "stars": {f"{k}_star": v for k, v in stars.items()},
            "new_this_month": new_this_month,
            "month_avg_rating": round(month_rating_sum / month_rating_n, 1) if month_rating_n else None,
            "response_rate_pct": round(replied / total * 100, 1) if total else None,
            "unanswered": unanswered,
        },
        "errors": None,
    }


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
