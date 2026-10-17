"""weekly COGS inventory counts

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-17
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_counts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), nullable=True),
        sa.Column("week_ending", sa.Date(), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("storage_path", sa.String(1024), nullable=True),
        sa.Column("category_totals", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "location_id", "week_ending", name="uq_inventory_count_week"),
    )
    op.create_index("ix_inventory_counts_tenant_id", "inventory_counts", ["tenant_id"])
    op.create_index("ix_inventory_counts_location_id", "inventory_counts", ["location_id"])
    op.create_index("ix_inventory_counts_week_ending", "inventory_counts", ["week_ending"])

    op.create_table(
        "inventory_count_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("count_id", UUID(as_uuid=True), sa.ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("item_name", sa.String(256), nullable=False),
        sa.Column("pack_size", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("cases", sa.Numeric(12, 3), nullable=True),
        sa.Column("packs", sa.Numeric(12, 3), nullable=True),
        sa.Column("weight", sa.Numeric(12, 3), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("extended_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_inventory_count_items_tenant_id", "inventory_count_items", ["tenant_id"])
    op.create_index("ix_inventory_count_items_count_id", "inventory_count_items", ["count_id"])


def downgrade() -> None:
    op.drop_table("inventory_count_items")
    op.drop_table("inventory_counts")
