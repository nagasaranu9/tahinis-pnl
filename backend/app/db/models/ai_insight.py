"""AI Insight model.

Stores Claude-generated insights. AI never modifies source financial records.
Every insight includes confidence_score and explanation (required by CLAUDE.md).
"""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin

INSIGHT_TYPES = [
    "expense_anomaly",
    "revenue_trend",
    "pnl_summary",
    "category_analysis",
    "reconciliation_summary",
    "labor_efficiency",
    "vendor_analysis",
]

INSIGHT_SEVERITIES = ["info", "warning", "critical"]


class AIInsight(Base, TenantMixin, TimestampMixin):
    """AI-generated business insight. Read-only after creation."""

    __tablename__ = "ai_insights"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)

    insight_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(50), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    # Required by CLAUDE.md: every AI output must include confidence_score + explanation
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)

    # Period the insight covers
    period_start: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    period_end: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Optional links to source records (AI must not modify these)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    expense_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reconciliation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    # User feedback
    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    is_helpful: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Which model generated this
    model_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
