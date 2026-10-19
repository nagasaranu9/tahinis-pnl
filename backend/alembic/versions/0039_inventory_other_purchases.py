"""inventory other (manual) purchases

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-19
"""
import sqlalchemy as sa

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_counts", sa.Column("other_purchases", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_counts", "other_purchases")
