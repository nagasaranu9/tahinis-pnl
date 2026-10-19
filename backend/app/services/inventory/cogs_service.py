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
from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.inventory import INVENTORY_CATEGORIES, InventoryCount

# Invoice expense category -> inventory category. "Food Cost" has no single
# inventory bucket, so it is allocated across the food categories by ending-
# inventory weight.
_FOOD_INV_CATEGORIES = ("Protein", "Cheesecake", "Grocery", "Produce")
_DIRECT_EXPENSE_MAP = {"Beverage Cost": "Beverage", "Packaging": "Packaging"}
_INVOICE_EXPENSE_CATEGORIES = ("Food Cost", "Beverage Cost", "Packaging")

_CENTS = Decimal("0.01")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENTS, rounding=ROUND_HALF_UP)


async def _net_sales(db: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None,
                     week_ending: date) -> Decimal:
    # Inventory is counted Sunday morning, so it reflects the completed week that
    # just ended — sum the 7 days up to (but not including) the count date.
    start = datetime.combine(week_ending - timedelta(days=7), time.min, tzinfo=timezone.utc)
    end = datetime.combine(week_ending - timedelta(days=1), time.max, tzinfo=timezone.utc)
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


def _purchase_window(week_ending: date, prior: InventoryCount | None) -> tuple[datetime, datetime]:
    """Invoices received during the count period: (prior count, this count].
    Without a prior count, the 7 days ending on the count date."""
    start_d = prior.week_ending if prior else (week_ending - timedelta(days=7))
    start = datetime.combine(start_d, time.min, tzinfo=timezone.utc) + (
        timedelta(days=1) if prior else timedelta(0)
    )
    end = datetime.combine(week_ending, time.max, tzinfo=timezone.utc)
    return start, end


async def _invoice_purchases(
    db: AsyncSession, tenant_id: uuid.UUID, location_id: uuid.UUID | None,
    week_ending: date, prior: InventoryCount | None, ending: dict[str, Decimal],
) -> tuple[dict[str, Decimal], int, Decimal]:
    """Per-inventory-category purchases from uploaded invoices/receipts in the
    count period (bank-statement expenses excluded). Returns (by_category,
    invoice_count, total)."""
    start, end = _purchase_window(week_ending, prior)
    conds = [
        Expense.tenant_id == tenant_id,
        Expense.expense_date >= start,
        Expense.expense_date <= end,
        Expense.category.in_(_INVOICE_EXPENSE_CATEGORIES),
        Document.document_type != "bank_statement",
    ]
    if location_id is not None:
        conds.append(Expense.location_id == location_id)
    rows = (await db.execute(
        select(Expense.category, Expense.amount, Expense.document_id)
        .join(Document, Expense.document_id == Document.id)
        .where(and_(*conds))
    )).all()

    by_cat = {c: Decimal("0") for c in INVENTORY_CATEGORIES}
    food_total = Decimal("0")
    total = Decimal("0")
    docs: set = set()
    for cat, amount, doc_id in rows:
        if amount is None:
            continue
        amt = Decimal(str(amount))
        total += amt
        if doc_id:
            docs.add(doc_id)
        inv_cat = _DIRECT_EXPENSE_MAP.get(cat)
        if inv_cat:
            by_cat[inv_cat] += amt
        else:  # Food Cost → allocate later
            food_total += amt

    if food_total > 0:
        weight_base = sum((ending[c] for c in _FOOD_INV_CATEGORIES), Decimal("0"))
        if weight_base > 0:
            for c in _FOOD_INV_CATEGORIES:
                by_cat[c] += food_total * (ending[c] / weight_base)
        else:
            even = food_total / Decimal(len(_FOOD_INV_CATEGORIES))
            for c in _FOOD_INV_CATEGORIES:
                by_cat[c] += even
    return by_cat, len(docs), _q(total)


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
    prior = await _prior_count(db, count.tenant_id, count.location_id, count.week_ending)
    opening = _ending_from(prior.category_totals) if prior else {c: Decimal("0") for c in INVENTORY_CATEGORIES}

    # Purchases precedence: (1) manual total override, allocated by ending-inv
    # weight; else (2) auto from uploaded invoices in the count period; the
    # sheet's own purchases column is a last-ditch fallback (usually blank).
    inv_purch, invoice_count, invoice_total = await _invoice_purchases(
        db, count.tenant_id, count.location_id, count.week_ending, prior, ending
    )
    sheet_purchases = {
        c: Decimal(str((count.category_totals.get(c) or {}).get("purchases", "0") or "0"))
        for c in INVENTORY_CATEGORIES
    }
    if count.purchases_override is not None:
        total_override = Decimal(str(count.purchases_override))
        weight_base = sum(ending.values(), Decimal("0"))
        if weight_base > 0:
            purchases = {c: _q(total_override * (ending[c] / weight_base)) for c in INVENTORY_CATEGORIES}
        else:
            even = _q(total_override / Decimal(len(INVENTORY_CATEGORIES)))
            purchases = {c: even for c in INVENTORY_CATEGORIES}
        purchases_source = "manual"
    elif invoice_total > 0:
        purchases = {c: _q(inv_purch[c]) for c in INVENTORY_CATEGORIES}
        purchases_source = "invoices"
    else:
        purchases = sheet_purchases
        purchases_source = "sheet"

    if count.net_sales_override is not None:
        net_sales = Decimal(str(count.net_sales_override))
    else:
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
        "net_sales_is_override": count.net_sales_override is not None,
        "purchases_is_override": count.purchases_override is not None,
        "purchases_source": purchases_source,
        "invoices": {"count": invoice_count, "total": _q(invoice_total)},
        "categories": rows,
        "totals": {
            "opening_inventory": _q(total_open),
            "purchases": _q(total_purch),
            "ending_inventory": _q(total_end),
            "cogs": _q(total_cogs),
            "cogs_pct": cogs_pct,
        },
    }
