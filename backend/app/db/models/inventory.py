"""Weekly COGS inventory-count uploads.

The tenant counts on-hand inventory once a week (the AFS inventory sheet) and
submits it for the coming week. Each upload is one `InventoryCount` (a week-
ending snapshot per location) with its priced line items in
`InventoryCountItem`. Weekly COGS is derived by chaining:

    COGS(week)  = opening inventory (prior week's ending count)
                + purchases (entered on the sheet, per category)
                − ending inventory (this week's count)

Net sales for the COGS % is pulled from existing revenue data at read time, so
it always reflects the latest sync. Nothing here feeds the bank-basis P&L — it
is a standalone inventory/COGS view.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin

# Canonical COGS categories the AFS sheet sections roll up into.
INVENTORY_CATEGORIES = (
    "Protein",
    "Cheesecake",
    "Grocery",
    "Produce",
    "Beverage",
    "Packaging",
)


class InventoryCount(Base, TimestampMixin, TenantMixin):
    """One weekly inventory-count submission (a priced snapshot)."""

    __tablename__ = "inventory_counts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "location_id", "week_ending",
            name="uq_inventory_count_week",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # The Saturday/period-end the count represents. Weeks chain by this date.
    week_ending: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    original_filename: Mapped[str | None] = mapped_column(String(512))
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    # Per-category ending inventory + sheet-entered purchases, cached for the
    # list view: {"Protein": {"ending": "1234.56", "purchases": "0.00"}, ...}
    category_totals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    items: Mapped[list["InventoryCountItem"]] = relationship(
        back_populates="count", cascade="all, delete-orphan"
    )


class InventoryCountItem(Base, TimestampMixin, TenantMixin):
    """One priced line from the count sheet."""

    __tablename__ = "inventory_count_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    count_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_counts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    pack_size: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str | None] = mapped_column(String(16))
    cases: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    packs: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    extended_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    count: Mapped["InventoryCount"] = relationship(back_populates="items")
