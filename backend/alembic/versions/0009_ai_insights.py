"""AI insights

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_insights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("insight_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False, server_default="info"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("period_start", sa.String(10), nullable=True),
        sa.Column("period_end", sa.String(10), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expense_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reconciliation_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_dismissed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("dismissed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_helpful", sa.Boolean, nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ai_insights_tenant_id", "ai_insights", ["tenant_id"])
    op.create_index("ix_ai_insights_insight_type", "ai_insights", ["tenant_id", "insight_type"])
    op.create_index("ix_ai_insights_location_id", "ai_insights", ["location_id"])
    op.create_index("ix_ai_insights_dismissed", "ai_insights", ["tenant_id", "is_dismissed"])

    op.execute("""
        CREATE TRIGGER set_ai_insights_updated_at
        BEFORE UPDATE ON ai_insights
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.drop_table("ai_insights")
