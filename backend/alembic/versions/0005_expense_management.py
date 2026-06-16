"""expense management

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("ai_suggested_category", sa.String(100), nullable=True),
        sa.Column("ai_confidence_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("ai_explanation", sa.Text, nullable=True),
        sa.Column("is_ai_categorized", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("user_overridden", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_expenses_tenant_id", "expenses", ["tenant_id"])
    op.create_index("ix_expenses_location_id", "expenses", ["location_id"])
    op.create_index("ix_expenses_document_id", "expenses", ["document_id"])
    op.create_index("ix_expenses_category", "expenses", ["category"])
    op.create_index("ix_expenses_tenant_category", "expenses", ["tenant_id", "category"])

    op.execute("""
        CREATE OR REPLACE FUNCTION update_expenses_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_expenses_updated_at
        BEFORE UPDATE ON expenses
        FOR EACH ROW EXECUTE FUNCTION update_expenses_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_expenses_updated_at ON expenses")
    op.execute("DROP FUNCTION IF EXISTS update_expenses_updated_at")
    op.drop_index("ix_expenses_tenant_category", "expenses")
    op.drop_index("ix_expenses_category", "expenses")
    op.drop_index("ix_expenses_document_id", "expenses")
    op.drop_index("ix_expenses_location_id", "expenses")
    op.drop_index("ix_expenses_tenant_id", "expenses")
    op.drop_table("expenses")
