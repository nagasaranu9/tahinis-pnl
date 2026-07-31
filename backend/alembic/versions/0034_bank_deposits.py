"""bank_deposits — money-in records for bank-basis P&L

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bank_deposits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deposit_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("is_revenue", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bank_deposits_tenant_id", "bank_deposits", ["tenant_id"])
    op.create_index("ix_bank_deposits_deposit_date", "bank_deposits", ["deposit_date"])
    op.create_index("ix_bank_deposits_location_id", "bank_deposits", ["location_id"])
    op.create_index("ix_bank_deposits_document_id", "bank_deposits", ["document_id"])


def downgrade() -> None:
    op.drop_table("bank_deposits")
