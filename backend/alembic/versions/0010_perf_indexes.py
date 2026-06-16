"""Performance indexes for high-frequency query paths.

P&L calculator filters toast_orders on (tenant_id, closed_at) and
expenses on (tenant_id, created_at). Without composite indexes these
become full table scans under load.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P&L date-range queries
    op.create_index(
        "ix_toast_orders_tenant_closed_at",
        "toast_orders",
        ["tenant_id", "closed_at"],
    )
    op.create_index(
        "ix_expenses_tenant_created_at",
        "expenses",
        ["tenant_id", "created_at"],
    )
    # Reconciliation flag listing (tenant + run + resolved status)
    op.create_index(
        "ix_reconciliation_flags_tenant_run",
        "reconciliation_flags",
        ["tenant_id", "run_id", "is_resolved"],
    )
    # AI insights listing (tenant + type + dismissed)
    op.create_index(
        "ix_ai_insights_tenant_type_dismissed",
        "ai_insights",
        ["tenant_id", "insight_type", "is_dismissed"],
    )
    # Google Ads metrics date range
    op.create_index(
        "ix_google_ads_daily_metrics_campaign_date",
        "google_ads_daily_metrics",
        ["campaign_id", "metric_date"],
    )
    # Google Reviews snapshots date range
    op.create_index(
        "ix_google_review_snapshots_tenant_date",
        "google_review_snapshots",
        ["tenant_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_toast_orders_tenant_closed_at", table_name="toast_orders")
    op.drop_index("ix_expenses_tenant_created_at", table_name="expenses")
    op.drop_index("ix_reconciliation_flags_tenant_run", table_name="reconciliation_flags")
    op.drop_index("ix_ai_insights_tenant_type_dismissed", table_name="ai_insights")
    op.drop_index("ix_google_ads_daily_metrics_campaign_date", table_name="google_ads_daily_metrics")
    op.drop_index("ix_google_review_snapshots_tenant_date", table_name="google_review_snapshots")
