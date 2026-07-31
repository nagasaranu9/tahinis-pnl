"""Partner profit/revenue-share configuration.

The bank-basis P&L splits both the top line (revenue) and the bottom line (net
profit) across the ownership group. Shares are tenant config — editable in the
UI — so a change in ownership reflows every month's split without a code change.
Percentages are stored as exact Decimals (e.g. 37.50) and are expected to sum to
100 per tenant; the calculator normalises defensively if they don't.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin


class PartnerShare(Base, TimestampMixin, TenantMixin):
    """One owner's percentage share of revenue and profit."""

    __tablename__ = "partner_shares"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_partner_share_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    share_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
