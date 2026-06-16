"""Add expense_date to expenses; P&L must filter by invoice date, not upload date.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "expenses",
        sa.Column("expense_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_expenses_tenant_expense_date",
        "expenses",
        ["tenant_id", "expense_date"],
    )

    # Backfill from linked document's document_date; fall back to created_at
    # for expenses with no document or no extracted date.
    op.execute(
        """
        UPDATE expenses e
        SET expense_date = COALESCE(d.document_date, e.created_at)
        FROM documents d
        WHERE e.document_id = d.id
        """
    )
    op.execute(
        """
        UPDATE expenses
        SET expense_date = created_at
        WHERE expense_date IS NULL
        """
    )

    op.alter_column("expenses", "expense_date", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_expenses_tenant_expense_date", table_name="expenses")
    op.drop_column("expenses", "expense_date")
