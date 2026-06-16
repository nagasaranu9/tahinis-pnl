"""Location extended fields: delivery IDs, Google Place, hours, rent, contacts.

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("uber_eats_id", sa.String(255), nullable=True))
    op.add_column("locations", sa.Column("skip_the_dishes_id", sa.String(255), nullable=True))
    op.add_column("locations", sa.Column("doordash_id", sa.String(255), nullable=True))
    op.add_column("locations", sa.Column("google_place_id", sa.String(512), nullable=True))
    op.add_column("locations", sa.Column("business_hours", postgresql.JSONB(), nullable=True))
    op.add_column(
        "locations",
        sa.Column("rent_monthly_incl_hst", sa.Numeric(15, 2), nullable=True),
    )
    op.add_column("locations", sa.Column("contacts", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("locations", "contacts")
    op.drop_column("locations", "rent_monthly_incl_hst")
    op.drop_column("locations", "business_hours")
    op.drop_column("locations", "google_place_id")
    op.drop_column("locations", "doordash_id")
    op.drop_column("locations", "skip_the_dishes_id")
    op.drop_column("locations", "uber_eats_id")
