"""add store_id to tenants

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("store_id", sa.String(10), nullable=True, unique=False),
    )
    op.create_index("ix_tenants_store_id", "tenants", ["store_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_store_id", table_name="tenants")
    op.drop_column("tenants", "store_id")
