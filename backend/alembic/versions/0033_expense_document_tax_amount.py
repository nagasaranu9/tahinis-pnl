"""expense + document tax_amount (HST/GST for ITC tracking)

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("expenses", sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True))
    op.add_column("documents", sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "tax_amount")
    op.drop_column("expenses", "tax_amount")
