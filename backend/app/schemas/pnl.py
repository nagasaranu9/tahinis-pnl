"""P&L report schemas."""
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict


class PnLLineItems(BaseModel):
    """All P&L line items. None when data is unavailable for a period."""

    gross_revenue: Optional[Decimal] = None
    total_discounts: Optional[Decimal] = None
    net_revenue: Optional[Decimal] = None

    cogs: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None

    labor_cost: Optional[Decimal] = None
    prime_cost: Optional[Decimal] = None

    operating_expenses: Optional[Decimal] = None

    ebitda: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None

    # Percentage breakdowns (of net_revenue)
    cogs_pct: Optional[Decimal] = None
    labor_pct: Optional[Decimal] = None
    prime_cost_pct: Optional[Decimal] = None
    ebitda_pct: Optional[Decimal] = None
    net_profit_pct: Optional[Decimal] = None


class ExpenseLineItem(BaseModel):
    vendor_name: Optional[str] = None
    amount: Decimal


class ExpenseCategoryBreakdown(BaseModel):
    category: str
    total: Decimal
    expense_count: int
    expenses: list[ExpenseLineItem] = []


class PnLReportResponse(BaseModel):
    """Full P&L report for a date range."""

    tenant_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    period_start: str
    period_end: str
    currency_code: str = "CAD"

    line_items: PnLLineItems
    expense_breakdown: list[ExpenseCategoryBreakdown] = []

    order_count: int = 0
    expense_count: int = 0

    # True only when at least one bank_statement document's date falls inside
    # the period. P&L numbers are computed either way — this just flags that
    # nothing has verified the expense/revenue data against the bank record.
    bank_statement_verified: bool = False
    bank_statement_warning: Optional[str] = None


class DailyRevenuePoint(BaseModel):
    date: str  # YYYY-MM-DD
    gross_revenue: Decimal
    net_revenue: Decimal
    void_amount: Decimal
    order_count: int


class DailyBreakdownResponse(BaseModel):
    period_start: str
    period_end: str
    points: list[DailyRevenuePoint] = []


class PnLSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    period_start: str
    period_end: str
    period_label: str
    gross_revenue: Optional[Decimal] = None
    total_discounts: Optional[Decimal] = None
    net_revenue: Optional[Decimal] = None
    cogs: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    labor_cost: Optional[Decimal] = None
    prime_cost: Optional[Decimal] = None
    operating_expenses: Optional[Decimal] = None
    ebitda: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None
    order_count: int
    expense_count: int
