"""Document pipeline: documents, ocr_results, extracted_line_items

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- documents ---
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual_upload"),
        sa.Column("source_id", sa.String(512), nullable=True),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("document_type", sa.String(50), nullable=False, server_default="other"),
        sa.Column("document_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duplicate_of", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_checksum", "documents", ["checksum_sha256"])
    op.create_index(
        "ix_documents_tenant_source_id",
        "documents",
        ["tenant_id", "source_id"],
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )

    # --- ocr_results ---
    op.create_table(
        "ocr_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="mock"),
        sa.Column("raw_response", postgresql.JSONB(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ocr_results_tenant_id", "ocr_results", ["tenant_id"])
    op.create_index("ix_ocr_results_document_id", "ocr_results", ["document_id"])

    # --- extracted_line_items ---
    op.create_table(
        "extracted_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ocr_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 4), nullable=True),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("confidence_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("manually_corrected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("corrected_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ocr_result_id"], ["ocr_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["corrected_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_line_items_tenant_id", "extracted_line_items", ["tenant_id"])
    op.create_index("ix_line_items_document_id", "extracted_line_items", ["document_id"])

    # updated_at triggers
    for table in ["documents", "extracted_line_items"]:
        op.execute(f"""
            CREATE TRIGGER trigger_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    for table in ["documents", "extracted_line_items"]:
        op.execute(f"DROP TRIGGER IF EXISTS trigger_{table}_updated_at ON {table}")

    op.drop_table("extracted_line_items")
    op.drop_table("ocr_results")
    op.drop_table("documents")
