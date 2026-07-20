"""tenant ocr_preferred_provider

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "ocr_preferred_provider",
            sa.String(length=20),
            nullable=False,
            server_default="auto",
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "ocr_preferred_provider")
