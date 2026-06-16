"""move store_id from tenants to locations

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove from tenants
    op.drop_index("ix_tenants_store_id", table_name="tenants")
    op.drop_column("tenants", "store_id")

    # Add to locations
    op.add_column(
        "locations",
        sa.Column("store_id", sa.String(10), nullable=True),
    )
    op.create_index("ix_locations_store_id", "locations", ["store_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_locations_store_id", table_name="locations")
    op.drop_column("locations", "store_id")
    op.add_column("tenants", sa.Column("store_id", sa.String(10), nullable=True))
    op.create_index("ix_tenants_store_id", "tenants", ["store_id"], unique=True)
