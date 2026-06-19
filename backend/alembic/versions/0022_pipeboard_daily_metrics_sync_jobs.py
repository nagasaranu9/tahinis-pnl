"""Create pipeboard_daily_metrics and pipeboard_sync_jobs tables.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeboard_daily_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_date", sa.String(10), nullable=False),
        sa.Column("spend", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Numeric(10, 2), nullable=True),
        sa.Column("conversion_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("ctr", sa.Numeric(5, 4), nullable=True),
        sa.Column("cpc", sa.Numeric(10, 4), nullable=True),
        sa.Column("roas", sa.Numeric(10, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["campaign_id"], ["pipeboard_campaigns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "campaign_id", "metric_date", name="uq_pipeboard_daily_metric"),
    )
    op.create_index("ix_pipeboard_daily_metrics_tenant_id", "pipeboard_daily_metrics", ["tenant_id"])
    op.create_index("ix_pipeboard_daily_metrics_campaign_id", "pipeboard_daily_metrics", ["campaign_id"])
    op.create_index("ix_pipeboard_daily_metrics_metric_date", "pipeboard_daily_metrics", ["metric_date"])

    op.create_table(
        "pipeboard_sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("pipeboard_platform", sa.String(20), nullable=True),
        sa.Column("date_from", sa.String(10), nullable=True),
        sa.Column("date_to", sa.String(10), nullable=True),
        sa.Column("metrics_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("campaigns_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeboard_sync_jobs_tenant_id", "pipeboard_sync_jobs", ["tenant_id"])
    op.create_index("ix_pipeboard_sync_tenant_status", "pipeboard_sync_jobs", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_table("pipeboard_sync_jobs")
    op.drop_table("pipeboard_daily_metrics")
