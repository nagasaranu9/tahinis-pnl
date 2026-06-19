"""Create pipeboard_category_mappings table.

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeboard_category_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeboard_platform", sa.String(20), nullable=False),
        sa.Column("pipeboard_campaign_type", sa.String(100), nullable=True),
        sa.Column("expense_category", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pipeboard_platform", "pipeboard_campaign_type", name="uq_pipeboard_mapping"),
    )
    op.create_index("ix_pipeboard_category_mappings_tenant_id", "pipeboard_category_mappings", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("pipeboard_category_mappings")
