"""partner_shares — ownership split config for bank-basis P&L

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-24
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("share_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_partner_share_tenant_name"),
    )
    op.create_index("ix_partner_shares_tenant_id", "partner_shares", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("partner_shares")
