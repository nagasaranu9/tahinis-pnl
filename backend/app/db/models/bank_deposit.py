"""Bank deposit (money-IN) records parsed from a bank statement.

The bank-basis P&L (tenant-elected) treats revenue as the cash that actually
lands in the business account — every CREDIT line on the bank statement — not
Toast POS sales. Card settlements, delivery-platform payouts, and online-order
deposits are each stored here with their channel so revenue can be split by
source and reconciled against the platform statements.

Only genuine sales settlements are marked ``is_revenue``. Non-sales credits
(loan drawdowns, owner capital injections, internal transfers, refunds) are
persisted too — so the statement reconciles line-for-line — but flagged
``is_revenue = False`` so they never inflate the top line.

Deposits are the money-in mirror of Expense (money-out): both are sourced from
the same statement import and keyed on the statement document, so re-importing a
month replaces its rows rather than duplicating them.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin

# Deposit channels that count as sales revenue on the bank-basis P&L. Mirrors the
# buckets produced by csv_statement._deposit_channel. Anything outside this set
# (loan/transfer/refund) is stored with is_revenue=False and excluded from the
# top line.
REVENUE_CHANNELS = frozenset({"toast", "square", "uber", "doordash", "skip", "gift", "loyalty"})


class BankDeposit(Base, TimestampMixin, TenantMixin):
    """One CREDIT line from a bank statement."""

    __tablename__ = "bank_deposits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deposit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    is_revenue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
