"""Create pipeboard_campaigns table.

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeboard_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pipeboard_platform", sa.String(20), nullable=False),
        sa.Column("pipeboard_campaign_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="ENABLED"),
        sa.Column("campaign_type", sa.String(100), nullable=True),
        sa.Column("daily_budget_limit", sa.Numeric(15, 2), nullable=True),
        sa.Column("lifetime_budget_limit", sa.Numeric(15, 2), nullable=True),
        sa.Column("spend_to_date", sa.Numeric(15, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pipeboard_platform", "pipeboard_campaign_id", name="uq_pipeboard_campaign"),
    )
    op.create_index("ix_pipeboard_campaigns_tenant_id", "pipeboard_campaigns", ["tenant_id"])
    op.create_index("ix_pipeboard_campaigns_location_id", "pipeboard_campaigns", ["location_id"])
    op.create_index("ix_pipeboard_campaigns_pipeboard_campaign_id", "pipeboard_campaigns", ["pipeboard_campaign_id"])


def downgrade() -> None:
    op.drop_table("pipeboard_campaigns")
