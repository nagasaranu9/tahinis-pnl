"""Widen integration credential token columns to TEXT.

Encrypted OAuth tokens (notably Outlook/Microsoft) exceed the previous
VARCHAR(2048) limit, causing StringDataRightTruncationError on insert.

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-13 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "integration_credentials",
        "access_token_encrypted",
        existing_type=sa.String(2048),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "integration_credentials",
        "refresh_token_encrypted",
        existing_type=sa.String(2048),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "integration_credentials",
        "refresh_token_encrypted",
        existing_type=sa.Text(),
        type_=sa.String(2048),
        existing_nullable=True,
    )
    op.alter_column(
        "integration_credentials",
        "access_token_encrypted",
        existing_type=sa.Text(),
        type_=sa.String(2048),
        existing_nullable=True,
    )
