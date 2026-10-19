"""inventory count purchases + net-sales overrides

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-18
"""
import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_counts", sa.Column("purchases_override", sa.Numeric(14, 2), nullable=True))
    op.add_column("inventory_counts", sa.Column("net_sales_override", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_counts", "net_sales_override")
    op.drop_column("inventory_counts", "purchases_override")
