"""External platform data models.

Stores daily snapshots from Google Business Profile and Google Ads.
All records are immutable after creation (historical snapshots).
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
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


class PipeboardAccount(Base, TenantMixin, TimestampMixin):
    """Pipeboard OAuth credentials per tenant."""

    __tablename__ = "pipeboard_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "pipeboard_account_id", name="uq_pipeboard_account"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # OAuth tokens (encrypted in app layer before INSERT)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(String(2048))
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(String(2048))
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Pipeboard identifiers
    pipeboard_account_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pipeboard_user_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Config
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text)


class PipeboardCategoryMapping(Base, TenantMixin, TimestampMixin):
    """Map Pipeboard platforms/campaign types to expense categories."""

    __tablename__ = "pipeboard_category_mappings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "pipeboard_platform", "pipeboard_campaign_type", name="uq_pipeboard_mapping"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # From Pipeboard
    pipeboard_platform: Mapped[str] = mapped_column(String(20), nullable=False)  # google_ads / meta_ads / tiktok_ads
    pipeboard_campaign_type: Mapped[Optional[str]] = mapped_column(String(100))  # SEARCH / DISPLAY / null = any

    # To expense category
    expense_category: Mapped[str] = mapped_column(String(100), nullable=False)  # Marketing / Brand Awareness / custom


class PipeboardCampaign(Base, TenantMixin, TimestampMixin):
    """Pipeboard campaign master record."""

    __tablename__ = "pipeboard_campaigns"
    __table_args__ = (
        UniqueConstraint("tenant_id", "pipeboard_platform", "pipeboard_campaign_id", name="uq_pipeboard_campaign"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Pipeboard identifiers
    pipeboard_platform: Mapped[str] = mapped_column(String(20), nullable=False)  # google_ads / meta_ads / tiktok_ads
    pipeboard_campaign_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Campaign state
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ENABLED")  # ENABLED / PAUSED / ARCHIVED
    campaign_type: Mapped[Optional[str]] = mapped_column(String(100))  # SEARCH / DISPLAY / PERFORMANCE_MAX / etc

    # Budget + pacing (at time of sync)
    daily_budget_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    lifetime_budget_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    spend_to_date: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))


class PipeboardDailyMetric(Base, TenantMixin):
    """Daily metrics per Pipeboard campaign (immutable snapshots)."""

    __tablename__ = "pipeboard_daily_metrics"
    __table_args__ = (
        UniqueConstraint("tenant_id", "campaign_id", "metric_date", name="uq_pipeboard_daily_metric"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("pipeboard_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )

    metric_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # YYYY-MM-DD

    # Spend + impressions + clicks
    spend: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(nullable=False, default=0)

    # Conversions (platform-specific)
    conversions: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    conversion_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))

    # Quality metrics
    ctr: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))  # Click-through rate
    cpc: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))  # Cost per click
    roas: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))  # Return on ad spend

    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class PipeboardSyncJob(Base, TenantMixin, TimestampMixin):
    """Background sync job tracking (like Toast sync jobs)."""

    __tablename__ = "pipeboard_sync_jobs"
    __table_args__ = (
        Index("ix_pipeboard_sync_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # incremental / historical
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # pending / running / complete / failed
    pipeboard_platform: Mapped[Optional[str]] = mapped_column(String(20))  # google_ads / meta_ads / tiktok_ads / null = all

    date_from: Mapped[Optional[str]] = mapped_column(String(10))  # YYYY-MM-DD
    date_to: Mapped[Optional[str]] = mapped_column(String(10))

    metrics_synced: Mapped[int] = mapped_column(nullable=False, default=0)
    campaigns_synced: Mapped[int] = mapped_column(nullable=False, default=0)

    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)

    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)  # user_id
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class PipeboardAlert(Base, TenantMixin):
    """Dashboard alert for Pipeboard integration issues."""

    __tablename__ = "pipeboard_alerts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # sync_failed / auth_failed / sync_stale / etc
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # info / warning / error / critical
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    is_dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dismissed_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)  # user_id

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


class PipeboardAuditLog(Base, TenantMixin):
    """Immutable audit log for Pipeboard events (auth, sync, config changes)."""

    __tablename__ = "pipeboard_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # oauth_connect / sync_start / sync_complete / auth_failed / etc
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info")  # info / warning / error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_detail: Mapped[Optional[str]] = mapped_column(Text)

    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)  # user_id for manual actions
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True)
