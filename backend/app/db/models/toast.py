from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, TenantMixin


class ToastSyncConfig(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    # Encrypted via IntegrationCredential; stored here for convenience lookup
    integration_credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True
    )
    toast_restaurant_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    historical_import_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    historical_import_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", name="uq_toast_sync_config_location"),
    )


class ToastSyncJob(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # historical | incremental | manual
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")  # pending|running|complete|failed
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    date_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    orders_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employees_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_entries_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


class ToastOrder(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    toast_restaurant_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    business_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # YYYYMMDD
    display_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    order_source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dining_option: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    table_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    server_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    tip_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    void_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    net_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="CAD", nullable=False)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    guest_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob

    items: Mapped[list[ToastOrderItem]] = relationship("ToastOrderItem", back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list[ToastPayment]] = relationship("ToastPayment", back_populates="order", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_order_guid"),
    )


class ToastOrderItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_order_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("toast_orders.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    menu_item_guid: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    pre_discount_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    discount_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    void_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_void: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="CAD", nullable=False)

    order: Mapped[ToastOrder] = relationship("ToastOrder", back_populates="items")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_order_item_guid"),
    )


class ToastPayment(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("toast_orders.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    payment_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # CREDIT, CASH, HOUSE_ACCOUNT, etc.
    card_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    tip_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="CAD", nullable=False)

    order: Mapped[ToastOrder] = relationship("ToastOrder", back_populates="payments")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_payment_guid"),
    )


class ToastEmployee(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    job_codes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    time_entries: Mapped[list[ToastTimeEntry]] = relationship("ToastTimeEntry", back_populates="employee")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_employee_guid"),
    )


class ToastTimeEntry(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_time_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("toast_employees.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    in_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    out_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    business_date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    job_code: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hours_regular: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    hours_overtime: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    declared_cash_tips: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    non_cash_tips: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    hourly_wage: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="CAD", nullable=False)
    auto_clocked_out: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    employee: Mapped[ToastEmployee] = relationship("ToastEmployee", back_populates="time_entries")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_time_entry_guid"),
    )


class ToastMenu(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_menus"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    menu_items: Mapped[list[ToastMenuItem]] = relationship("ToastMenuItem", back_populates="menu")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_menu_guid"),
    )


class ToastMenuItem(Base, TimestampMixin, TenantMixin):
    __tablename__ = "toast_menu_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("toast_menus.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    toast_guid: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sku: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plu: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), default="CAD", nullable=False)

    menu: Mapped[ToastMenu] = relationship("ToastMenu", back_populates="menu_items")

    __table_args__ = (
        UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_menu_item_guid"),
    )
