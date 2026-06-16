"""P&L snapshot model.

Stores pre-computed monthly P&L statements for fast retrieval.
On-the-fly reports are computed by PnLCalculator without persisting.
"""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.base import TenantMixin, TimestampMixin


class PnLSnapshot(Base, TenantMixin, TimestampMixin):
    """Monthly P&L snapshot stored by the Celery beat task."""

    __tablename__ = "pnl_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", "period_start", name="uq_pnl_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)

    # Period — stored as strings (YYYY-MM-DD)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "2024-06"

    # Revenue
    gross_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    total_discounts: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    net_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    # Cost lines
    cogs: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    gross_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    labor_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    prime_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    operating_expenses: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    ebitda: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    net_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    # Metadata
    order_count: Mapped[int] = mapped_column(nullable=False, default=0)
    expense_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
