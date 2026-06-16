"""reconciliation engine

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("triggered_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("documents_checked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expenses_checked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("toast_orders_checked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("flags_raised", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_sales_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_expense_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_variance", sa.Numeric(15, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reconciliation_runs_tenant_id", "reconciliation_runs", ["tenant_id"])
    op.create_index("ix_reconciliation_runs_location_id", "reconciliation_runs", ["location_id"])
    op.create_index("ix_reconciliation_runs_status", "reconciliation_runs", ["status"])

    op.create_table(
        "reconciliation_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("flag_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expense_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("expenses.id", ondelete="SET NULL"), nullable=True),
        sa.Column("toast_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("toast_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reconciliation_flags_tenant_id", "reconciliation_flags", ["tenant_id"])
    op.create_index("ix_reconciliation_flags_run_id", "reconciliation_flags", ["run_id"])
    op.create_index("ix_reconciliation_flags_flag_type", "reconciliation_flags", ["flag_type"])
    op.create_index("ix_reconciliation_flags_is_resolved", "reconciliation_flags", ["is_resolved"])

    for table in ("reconciliation_runs", "reconciliation_flags"):
        fn = f"update_{table}_updated_at"
        trg = f"trg_{table}_updated_at"
        op.execute(f"""
            CREATE OR REPLACE FUNCTION {fn}()
            RETURNS TRIGGER AS $$
            BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute(f"""
            CREATE TRIGGER {trg}
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION {fn}();
        """)


def downgrade() -> None:
    for table in ("reconciliation_flags", "reconciliation_runs"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS update_{table}_updated_at")

    op.drop_index("ix_reconciliation_flags_is_resolved", "reconciliation_flags")
    op.drop_index("ix_reconciliation_flags_flag_type", "reconciliation_flags")
    op.drop_index("ix_reconciliation_flags_run_id", "reconciliation_flags")
    op.drop_index("ix_reconciliation_flags_tenant_id", "reconciliation_flags")
    op.drop_table("reconciliation_flags")

    op.drop_index("ix_reconciliation_runs_status", "reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_location_id", "reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_tenant_id", "reconciliation_runs")
    op.drop_table("reconciliation_runs")
