"""External platform data (Google Reviews + Google Ads)

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_review_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("snapshot_date", sa.String(10), nullable=False),
        sa.Column("rating_average", sa.Numeric(3, 2), nullable=True),
        sa.Column("review_count_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("new_reviews_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("neutral_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("google_place_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "location_id", "snapshot_date", name="uq_review_snapshot"),
    )
    op.create_index("ix_review_snapshots_tenant_id", "google_review_snapshots", ["tenant_id"])
    op.create_index("ix_review_snapshots_date", "google_review_snapshots", ["tenant_id", "snapshot_date"])

    op.create_table(
        "google_ads_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("google_campaign_id", sa.String(100), nullable=False),
        sa.Column("google_customer_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ENABLED"),
        sa.Column("campaign_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "google_campaign_id", name="uq_ads_campaign"),
    )
    op.create_index("ix_ads_campaigns_tenant_id", "google_ads_campaigns", ["tenant_id"])

    op.create_table(
        "google_ads_daily_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("google_ads_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_date", sa.String(10), nullable=False),
        sa.Column("spend", sa.Numeric(15, 2), nullable=True),
        sa.Column("impressions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(10, 2), nullable=True),
        sa.Column("roas", sa.Numeric(10, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "campaign_id", "metric_date", name="uq_ads_daily_metric"),
    )
    op.create_index("ix_ads_daily_metrics_tenant_id", "google_ads_daily_metrics", ["tenant_id"])
    op.create_index("ix_ads_daily_metrics_date", "google_ads_daily_metrics", ["campaign_id", "metric_date"])

    op.execute("""
        CREATE TRIGGER set_google_review_snapshots_updated_at
        BEFORE UPDATE ON google_review_snapshots
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER set_google_ads_campaigns_updated_at
        BEFORE UPDATE ON google_ads_campaigns
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER set_google_ads_daily_metrics_updated_at
        BEFORE UPDATE ON google_ads_daily_metrics
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.drop_table("google_ads_daily_metrics")
    op.drop_table("google_ads_campaigns")
    op.drop_table("google_review_snapshots")
