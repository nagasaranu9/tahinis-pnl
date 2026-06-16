"""P&L snapshots

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pnl_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_start", sa.String(10), nullable=False),
        sa.Column("period_end", sa.String(10), nullable=False),
        sa.Column("period_label", sa.String(50), nullable=False),
        sa.Column("gross_revenue", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_discounts", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_revenue", sa.Numeric(15, 2), nullable=True),
        sa.Column("cogs", sa.Numeric(15, 2), nullable=True),
        sa.Column("gross_profit", sa.Numeric(15, 2), nullable=True),
        sa.Column("labor_cost", sa.Numeric(15, 2), nullable=True),
        sa.Column("prime_cost", sa.Numeric(15, 2), nullable=True),
        sa.Column("operating_expenses", sa.Numeric(15, 2), nullable=True),
        sa.Column("ebitda", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_profit", sa.Numeric(15, 2), nullable=True),
        sa.Column("order_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expense_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "location_id", "period_start", name="uq_pnl_snapshot"),
    )
    op.create_index("ix_pnl_snapshots_tenant_id", "pnl_snapshots", ["tenant_id"])
    op.create_index("ix_pnl_snapshots_location_id", "pnl_snapshots", ["location_id"])
    op.create_index("ix_pnl_snapshots_period_label", "pnl_snapshots", ["tenant_id", "period_label"])

    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER set_pnl_snapshots_updated_at
        BEFORE UPDATE ON pnl_snapshots
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.drop_table("pnl_snapshots")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at() CASCADE")
