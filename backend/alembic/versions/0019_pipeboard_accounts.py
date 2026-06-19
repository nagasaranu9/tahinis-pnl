"""Create pipeboard_accounts table.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeboard_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("access_token_encrypted", sa.String(2048), nullable=True),
        sa.Column("refresh_token_encrypted", sa.String(2048), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pipeboard_account_id", sa.String(255), nullable=False),
        sa.Column("pipeboard_user_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pipeboard_account_id", name="uq_pipeboard_account"),
    )
    op.create_index("ix_pipeboard_accounts_tenant_id", "pipeboard_accounts", ["tenant_id"])
    op.create_index("ix_pipeboard_accounts_pipeboard_account_id", "pipeboard_accounts", ["pipeboard_account_id"])


def downgrade() -> None:
    op.drop_table("pipeboard_accounts")
