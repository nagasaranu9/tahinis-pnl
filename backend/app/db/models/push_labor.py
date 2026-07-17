"""
PushOperations labor models.

Labor cost is pulled from the PushOperations platform API
(`GET /labour/employee`), which returns one row per employee, per day, per
labour type (reg / ot / otw / vac). That grain is stored verbatim in
`push_labour_employee_daily` so the P&L can aggregate it, and so scheduled vs
actual variance can be computed per position without a second API round-trip.

The API is the source of truth for Labor Cost once the integration is active;
the payroll CSV/OCR path (see services/labor/pushops_import.py) becomes a
month-end cross-check rather than the primary feed.

Punches are edited retroactively in PushOperations (managers fix missed clock-
outs days later), so rows are upserted on their natural key rather than
inserted. Re-syncing a date range corrects it in place and never duplicates.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin

# Labour types returned by the API. "reg" regular, "ot" overtime, "otw"
# overtime (weekly threshold), "vac" vacation accrual, "stat" statutory pay.
# Unknown types are stored as-is rather than dropped — a new payroll code must
# never silently vanish from the Labor line.
LABOUR_TYPE_OVERTIME = frozenset({"ot", "otw"})


class PushLabourEmployeeDaily(Base, TimestampMixin, TenantMixin):
    """One employee's cost + hours for one business date and one labour type."""

    __tablename__ = "push_labour_employee_daily"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    push_company_id: Mapped[int] = mapped_column(Integer, nullable=False)

    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    employee_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Part of the upsert natural key, so it must never be NULL: Postgres treats
    # NULLs as distinct in a unique constraint, which would let a null-position
    # row duplicate on every re-sync instead of updating in place. The API has
    # always populated positionId; 0 is the sentinel if it ever does not.
    position_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    position_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    labour_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # The API returns unrounded floats (e.g. 153.84615384615). Quantized to 2dp
    # at ingest — see push_client._to_money. Never store float money.
    cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "push_company_id",
            "business_date",
            "employee_id",
            "position_id",
            "labour_type",
            name="uq_push_labour_employee_daily",
        ),
    )


class PushSyncConfig(Base, TimestampMixin, TenantMixin):
    """Per-location PushOperations sync settings and cursor state."""

    __tablename__ = "push_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=True
    )
    push_company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    push_company_uuid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    push_company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    historical_import_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    historical_import_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "push_company_id", name="uq_push_sync_config_company"),
    )


class PushSyncJob(Base, TimestampMixin, TenantMixin):
    """Audit trail for every Push sync run — required for financial traceability."""

    __tablename__ = "push_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    push_company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # "historical" | "incremental" | "realtime" | "manual"
    job_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # "running" | "succeeded" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rows_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
