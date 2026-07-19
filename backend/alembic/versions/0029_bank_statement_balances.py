"""Bank statement balance summary columns

Adds opening/closing balance and deposit/withdrawal totals to documents.
Populated at OCR time for bank statements; consumed by the reconciliation
engine for balance-chain (month N closing == month N+1 opening) and
in-statement arithmetic verification.

Revision ID: 0029
Revises: 0028
"""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("opening_balance", sa.Numeric(15, 2), nullable=True))
    op.add_column("documents", sa.Column("closing_balance", sa.Numeric(15, 2), nullable=True))
    op.add_column("documents", sa.Column("total_deposits", sa.Numeric(15, 2), nullable=True))
    op.add_column("documents", sa.Column("total_withdrawals", sa.Numeric(15, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "total_withdrawals")
    op.drop_column("documents", "total_deposits")
    op.drop_column("documents", "closing_balance")
    op.drop_column("documents", "opening_balance")
