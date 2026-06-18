from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin

# Flag types raised during reconciliation
FLAG_TYPES = {
    "missing_invoice",       # expense has no linked document
    "duplicate_invoice",     # document flagged as duplicate
    "duplicate_expense",     # multiple expenses linked to same document
    "uncategorized_expense", # expense has no category after AI pass
    "suspicious_amount",     # amount > 3 stddev from vendor mean
    "unmatched_sale",        # Toast sale day with no expense document
    "unverified_payroll",    # Payroll expense with no matching bank-statement debit
}

FLAG_SEVERITIES = {"low", "medium", "high", "critical"}


class ReconciliationRun(Base, TenantMixin, TimestampMixin):
    __tablename__ = "reconciliation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Counters
    documents_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expenses_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    toast_orders_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flags_raised: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Totals (Decimal for auditability)
    total_sales_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_expense_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    net_variance: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    flags: Mapped[list[ReconciliationFlag]] = relationship(
        "ReconciliationFlag", back_populates="run", cascade="all, delete-orphan", lazy="select"
    )


class ReconciliationFlag(Base, TenantMixin, TimestampMixin):
    __tablename__ = "reconciliation_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    flag_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional links to source records
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    expense_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True
    )
    toast_order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("toast_orders.id", ondelete="SET NULL"), nullable=True
    )

    # Resolution
    is_resolved: Mapped[bool] = mapped_column(
        __import__("sqlalchemy").Boolean, nullable=False, default=False, index=True
    )
    resolved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped[ReconciliationRun] = relationship("ReconciliationRun", back_populates="flags")
