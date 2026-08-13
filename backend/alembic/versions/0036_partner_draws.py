"""partner draws + vehicle flag

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "partner_shares",
        sa.Column("gets_vehicle", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "partner_draws",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("note", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", "period_start", "period_end", name="uq_partner_draw_period"),
    )
    op.create_index("ix_partner_draws_tenant_id", "partner_draws", ["tenant_id"])
    op.create_index("ix_partner_draws_period_start", "partner_draws", ["period_start"])


def downgrade() -> None:
    op.drop_table("partner_draws")
    op.drop_column("partner_shares", "gets_vehicle")
