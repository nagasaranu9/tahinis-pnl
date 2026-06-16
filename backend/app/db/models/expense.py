import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin

EXPENSE_CATEGORIES = {
    "Food Cost",
    "Beverage Cost",
    "Packaging",
    "Cleaning",
    "Utilities",
    "Rent",
    "Marketing",
    "Payroll",
    "Repairs",
    "Maintenance",
    "Insurance",
    "Software",
    "Professional Services",
    "Royalties",
    "Miscellaneous",
}


class Expense(Base, TenantMixin, TimestampMixin):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Financial data mirrored from document (read-only copy — source stays in documents table)
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")

    # Invoice/transaction date — drives P&L period assignment. Distinct from
    # created_at (upload timestamp), which must never be used for period filtering.
    expense_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Categorization
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    ai_suggested_category: Mapped[str | None] = mapped_column(String(100))
    ai_confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    ai_explanation: Mapped[str | None] = mapped_column(Text)
    is_ai_categorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Audit
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    document: Mapped["Document"] = relationship("Document", foreign_keys=[document_id], lazy="select")  # type: ignore[name-defined]
