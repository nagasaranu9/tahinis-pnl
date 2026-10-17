"""Weekly COGS computation from chained inventory counts.

COGS(week) = opening inventory (prior week's ending count)
           + purchases (entered on this week's sheet, per category)
           − ending inventory (this week's count)

Net sales for the COGS % is pulled live from bank-deposit revenue (the tenant's
elected revenue basis) for the 7 days ending on the count date.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.bank_deposit import BankDeposit
from app.db.models.inventory import INVENTORY_CATEGORIES, InventoryCount

_CENTS = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENTS, rounding=ROUND_HALF_UP)


async def _net_sales(db: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None,
                     week_ending: date) -> Decimal:
    start = datetime.combine(week_ending - timedelta(days=6), time.min, tzinfo=timezone.utc)
    end = datetime.combine(week_ending, time.max, tzinfo=timezone.utc)
    conds = [
        BankDeposit.tenant_id == tenant_id,
        BankDeposit.is_revenue.is_(True),
        BankDeposit.deposit_date >= start,
        BankDeposit.deposit_date <= end,
    ]
    if location_id is not None:
        conds.append(BankDeposit.location_id == location_id)
    total = await db.scalar(
        select(func.coalesce(func.sum(BankDeposit.amount), 0)).where(and_(*conds))
    )
    return _q(Decimal(str(total or 0)))


async def _prior_count(db: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None,
                       week_ending: date) -> InventoryCount | None:
    conds = [
        InventoryCount.tenant_id == tenant_id,
        InventoryCount.week_ending < week_ending,
    ]
    if location_id is not None:
        conds.append(InventoryCount.location_id == location_id)
    return (await db.execute(
        select(InventoryCount).where(and_(*conds))
        .order_by(InventoryCount.week_ending.desc()).limit(1)
    )).scalars().first()


def _ending_from(totals: dict) -> dict[str, Decimal]:
    """category_totals JSON -> {category: ending Decimal}."""
    out: dict[str, Decimal] = {}
    for c in INVENTORY_CATEGORIES:
        cell = (totals or {}).get(c) or {}
        out[c] = Decimal(str(cell.get("ending", "0") or "0"))
    return out


async def compute_cogs(db: AsyncSession, count: InventoryCount) -> dict:
    """Per-category + total COGS for one weekly count, with net sales & %."""
    ending = _ending_from(count.category_totals)
    purchases = {
        c: Decimal(str((count.category_totals.get(c) or {}).get("purchases", "0") or "0"))
        for c in INVENTORY_CATEGORIES
    }
    prior = await _prior_count(db, count.tenant_id, count.location_id, count.week_ending)
    opening = _ending_from(prior.category_totals) if prior else {c: Decimal("0") for c in INVENTORY_CATEGORIES}

    net_sales = await _net_sales(db, count.tenant_id, count.location_id, count.week_ending)

    rows = []
    total_cogs = Decimal("0")
    total_open = total_purch = total_end = Decimal("0")
    for c in INVENTORY_CATEGORIES:
        cogs = opening[c] + purchases[c] - ending[c]
        total_cogs += cogs
        total_open += opening[c]
        total_purch += purchases[c]
        total_end += ending[c]
        rows.append({
            "category": c,
            "opening_inventory": _q(opening[c]),
            "purchases": _q(purchases[c]),
            "ending_inventory": _q(ending[c]),
            "cogs": _q(cogs),
        })

    cogs_pct = (
        _q(total_cogs / net_sales * Decimal("100")) if net_sales > 0 else None
    )
    return {
        "week_ending": count.week_ending.isoformat(),
        "has_prior_week": prior is not None,
        "net_sales": _q(net_sales),
        "categories": rows,
        "totals": {
            "opening_inventory": _q(total_open),
            "purchases": _q(total_purch),
            "ending_inventory": _q(total_end),
            "cogs": _q(total_cogs),
            "cogs_pct": cogs_pct,
        },
    }
