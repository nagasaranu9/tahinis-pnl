"""External platform data models.

Stores daily snapshots from Google Business Profile and Google Ads.
All records are immutable after creation (historical snapshots).
"""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.base import TenantMixin, TimestampMixin
from sqlalchemy.dialects.postgresql import UUID as PGUUID


class GoogleReviewSnapshot(Base, TenantMixin, TimestampMixin):
    """Daily snapshot of Google Business Profile review metrics."""

    __tablename__ = "google_review_snapshots"
    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", "snapshot_date", name="uq_review_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD

    rating_average: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), nullable=True)
    review_count_total: Mapped[int] = mapped_column(nullable=False, default=0)
    new_reviews_count: Mapped[int] = mapped_column(nullable=False, default=0)
    positive_count: Mapped[int] = mapped_column(nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(nullable=False, default=0)

    # Raw source reference (place_id for the Google Business Profile)
    google_place_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class GoogleAdsCampaign(Base, TenantMixin, TimestampMixin):
    """Google Ads campaign master record."""

    __tablename__ = "google_ads_campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "google_campaign_id", name="uq_ads_campaign"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    google_campaign_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    google_customer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ENABLED")  # ENABLED/PAUSED/REMOVED
    campaign_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class GoogleAdsDailyMetric(Base, TenantMixin, TimestampMixin):
    """Daily performance metrics for a Google Ads campaign."""

    __tablename__ = "google_ads_daily_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "campaign_id", "metric_date", name="uq_ads_daily_metric"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    metric_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD

    spend: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    impressions: Mapped[int] = mapped_column(nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(nullable=False, default=0)
    conversions: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    roas: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
