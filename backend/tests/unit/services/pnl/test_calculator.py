"""Unit tests for PnLCalculator.

All DB loaders are patched — no DB required.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.expense import Expense
from app.db.models.toast import ToastOrder
from app.services.pnl.calculator import PnLCalculator

TENANT_ID = uuid.uuid4()
PERIOD_START = datetime(2024, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc)


def _make_calculator() -> PnLCalculator:
    db = AsyncMock()
    calc = PnLCalculator(db)
    return calc


def _order(
    *,
    net_amount: Decimal = Decimal("1000.00"),
    discount_amount: Decimal = Decimal("0.00"),
    is_void: bool = False,
) -> ToastOrder:
    o = MagicMock(spec=ToastOrder)
    o.id = uuid.uuid4()
    o.is_void = is_void
    o.net_amount = net_amount
    o.discount_amount = discount_amount
    o.closed_at = PERIOD_START
    return o


def _expense(*, category: str | None, amount: Decimal) -> Expense:
    e = MagicMock(spec=Expense)
    e.id = uuid.uuid4()
    e.category = category
    e.amount = amount
    return e


async def _compute(calc: PnLCalculator, orders: list, expenses: list):
    calc._load_orders = AsyncMock(return_value=orders)
    calc._load_expenses = AsyncMock(return_value=expenses)
    return await calc.compute(
        tenant_id=TENANT_ID,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
    )


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_net_revenue_equals_sum_of_net_amounts():
    calc = _make_calculator()
    orders = [_order(net_amount=Decimal("800.00")), _order(net_amount=Decimal("500.00"))]
    report = await _compute(calc, orders, [])
    assert report.line_items.net_revenue == Decimal("1300.00")


@pytest.mark.asyncio
async def test_gross_revenue_adds_back_discounts():
    calc = _make_calculator()
    # net_amount already has discount removed; gross = net + discount
    orders = [_order(net_amount=Decimal("900.00"), discount_amount=Decimal("100.00"))]
    report = await _compute(calc, orders, [])
    assert report.line_items.gross_revenue == Decimal("1000.00")
    assert report.line_items.total_discounts == Decimal("100.00")
    assert report.line_items.net_revenue == Decimal("900.00")


@pytest.mark.asyncio
async def test_void_orders_excluded_from_revenue():
    calc = _make_calculator()
    active = _order(net_amount=Decimal("600.00"))
    voided = _order(net_amount=Decimal("400.00"), is_void=True)
    report = await _compute(calc, [active, voided], [])
    assert report.line_items.net_revenue == Decimal("600.00")
    assert report.order_count == 1


@pytest.mark.asyncio
async def test_zero_orders_returns_none_revenue():
    calc = _make_calculator()
    report = await _compute(calc, [], [])
    assert report.line_items.net_revenue is None
    assert report.line_items.gross_revenue is None


# ---------------------------------------------------------------------------
# COGS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cogs_sums_food_beverage_packaging():
    calc = _make_calculator()
    expenses = [
        _expense(category="Food Cost", amount=Decimal("300.00")),
        _expense(category="Beverage Cost", amount=Decimal("100.00")),
        _expense(category="Packaging", amount=Decimal("50.00")),
        _expense(category="Utilities", amount=Decimal("200.00")),  # not COGS
    ]
    report = await _compute(calc, [_order()], expenses)
    assert report.line_items.cogs == Decimal("450.00")


@pytest.mark.asyncio
async def test_gross_profit_equals_revenue_minus_cogs():
    calc = _make_calculator()
    expenses = [_expense(category="Food Cost", amount=Decimal("400.00"))]
    orders = [_order(net_amount=Decimal("1000.00"))]
    report = await _compute(calc, orders, expenses)
    assert report.line_items.gross_profit == Decimal("600.00")


# ---------------------------------------------------------------------------
# Labor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_labor_cost_from_payroll_expenses():
    calc = _make_calculator()
    expenses = [
        _expense(category="Payroll", amount=Decimal("2000.00")),
        _expense(category="Food Cost", amount=Decimal("500.00")),
    ]
    report = await _compute(calc, [_order(net_amount=Decimal("5000.00"))], expenses)
    assert report.line_items.labor_cost == Decimal("2000.00")


@pytest.mark.asyncio
async def test_prime_cost_equals_cogs_plus_labor():
    calc = _make_calculator()
    expenses = [
        _expense(category="Food Cost", amount=Decimal("300.00")),
        _expense(category="Payroll", amount=Decimal("700.00")),
    ]
    orders = [_order(net_amount=Decimal("2000.00"))]
    report = await _compute(calc, orders, expenses)
    assert report.line_items.prime_cost == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Operating expenses & EBITDA
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operating_expenses_exclude_cogs_and_payroll():
    calc = _make_calculator()
    expenses = [
        _expense(category="Food Cost", amount=Decimal("300.00")),
        _expense(category="Payroll", amount=Decimal("500.00")),
        _expense(category="Utilities", amount=Decimal("100.00")),
        _expense(category="Rent", amount=Decimal("200.00")),
        _expense(category="Software", amount=Decimal("50.00")),
    ]
    orders = [_order(net_amount=Decimal("3000.00"))]
    report = await _compute(calc, orders, expenses)
    assert report.line_items.operating_expenses == Decimal("350.00")


@pytest.mark.asyncio
async def test_ebitda_calculation():
    """EBITDA = Net Revenue - COGS - Labor - Opex."""
    calc = _make_calculator()
    orders = [_order(net_amount=Decimal("5000.00"))]
    expenses = [
        _expense(category="Food Cost", amount=Decimal("1000.00")),  # COGS
        _expense(category="Payroll", amount=Decimal("1500.00")),  # Labor
        _expense(category="Rent", amount=Decimal("500.00")),  # Opex
    ]
    report = await _compute(calc, orders, expenses)
    expected = Decimal("5000") - Decimal("1000") - Decimal("1500") - Decimal("500")
    assert report.line_items.ebitda == expected


@pytest.mark.asyncio
async def test_negative_ebitda_when_expenses_exceed_revenue():
    calc = _make_calculator()
    orders = [_order(net_amount=Decimal("1000.00"))]
    expenses = [_expense(category="Rent", amount=Decimal("5000.00"))]
    report = await _compute(calc, orders, expenses)
    assert report.line_items.ebitda is not None
    assert report.line_items.ebitda < 0


# ---------------------------------------------------------------------------
# Percentage calculations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_percentage_fields_populated():
    calc = _make_calculator()
    orders = [_order(net_amount=Decimal("1000.00"))]
    expenses = [
        _expense(category="Food Cost", amount=Decimal("300.00")),
        _expense(category="Payroll", amount=Decimal("200.00")),
    ]
    report = await _compute(calc, orders, expenses)
    li = report.line_items
    assert li.cogs_pct == Decimal("30.00")
    assert li.labor_pct == Decimal("20.00")
    assert li.prime_cost_pct == Decimal("50.00")


@pytest.mark.asyncio
async def test_percentage_none_when_no_revenue():
    calc = _make_calculator()
    expenses = [_expense(category="Food Cost", amount=Decimal("300.00"))]
    report = await _compute(calc, [], expenses)
    assert report.line_items.cogs_pct is None


# ---------------------------------------------------------------------------
# Expense breakdown
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expense_breakdown_groups_by_category():
    calc = _make_calculator()
    expenses = [
        _expense(category="Food Cost", amount=Decimal("100.00")),
        _expense(category="Food Cost", amount=Decimal("200.00")),
        _expense(category="Utilities", amount=Decimal("50.00")),
    ]
    report = await _compute(calc, [_order()], expenses)
    breakdown = {b.category: b for b in report.expense_breakdown}
    assert breakdown["Food Cost"].total == Decimal("300.00")
    assert breakdown["Food Cost"].expense_count == 2
    assert breakdown["Utilities"].total == Decimal("50.00")


@pytest.mark.asyncio
async def test_uncategorized_expense_included_in_breakdown():
    calc = _make_calculator()
    expenses = [_expense(category=None, amount=Decimal("75.00"))]
    report = await _compute(calc, [_order()], expenses)
    categories = [b.category for b in report.expense_breakdown]
    assert "Uncategorized" in categories


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_order_count_excludes_voids():
    calc = _make_calculator()
    orders = [_order(), _order(), _order(is_void=True)]
    report = await _compute(calc, orders, [])
    assert report.order_count == 2


@pytest.mark.asyncio
async def test_expense_count_correct():
    calc = _make_calculator()
    expenses = [_expense(category="Rent", amount=Decimal("500.00"))] * 5
    report = await _compute(calc, [], expenses)
    assert report.expense_count == 5
