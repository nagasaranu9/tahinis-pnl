"""email and drive sync

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sync_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("integration_credential_id", UUID(as_uuid=True), sa.ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_address", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("history_id", sa.String(255), nullable=True),
        sa.Column("delta_link", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "provider", "email_address", name="uq_email_sync_config"),
    )
    op.create_index("ix_email_sync_configs_tenant_id", "email_sync_configs", ["tenant_id"])
    op.execute("""
        CREATE TRIGGER update_email_sync_configs_updated_at
        BEFORE UPDATE ON email_sync_configs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "email_sync_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("email_sync_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attachments_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_sync_jobs_tenant_id", "email_sync_jobs", ["tenant_id"])
    op.create_index("ix_email_sync_jobs_config_id", "email_sync_jobs", ["config_id"])
    op.execute("""
        CREATE TRIGGER update_email_sync_jobs_updated_at
        BEFORE UPDATE ON email_sync_jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "email_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("email_sync_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_message_id", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(1000), nullable=True),
        sa.Column("sender", sa.String(500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "provider", "provider_message_id", name="uq_email_message"),
    )
    op.create_index("ix_email_messages_tenant_id", "email_messages", ["tenant_id"])
    op.create_index("ix_email_messages_config_id", "email_messages", ["config_id"])
    op.create_index("ix_email_messages_received_at", "email_messages", ["received_at"])
    op.execute("""
        CREATE TRIGGER update_email_messages_updated_at
        BEFORE UPDATE ON email_messages
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "email_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("provider_attachment_id", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_attachments_tenant_id", "email_attachments", ["tenant_id"])
    op.create_index("ix_email_attachments_message_id", "email_attachments", ["message_id"])
    op.execute("""
        CREATE TRIGGER update_email_attachments_updated_at
        BEFORE UPDATE ON email_attachments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "drive_sync_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_credential_id", UUID(as_uuid=True), sa.ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email_address", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("page_token", sa.String(500), nullable=True),
        sa.Column("folder_ids", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "email_address", name="uq_drive_sync_config"),
    )
    op.create_index("ix_drive_sync_configs_tenant_id", "drive_sync_configs", ["tenant_id"])
    op.execute("""
        CREATE TRIGGER update_drive_sync_configs_updated_at
        BEFORE UPDATE ON drive_sync_configs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "drive_sync_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_id", UUID(as_uuid=True), sa.ForeignKey("drive_sync_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("files_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicates_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_drive_sync_jobs_tenant_id", "drive_sync_jobs", ["tenant_id"])
    op.execute("""
        CREATE TRIGGER update_drive_sync_jobs_updated_at
        BEFORE UPDATE ON drive_sync_jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    for table in [
        "drive_sync_jobs",
        "drive_sync_configs",
        "email_attachments",
        "email_messages",
        "email_sync_jobs",
        "email_sync_configs",
    ]:
        op.drop_table(table)
