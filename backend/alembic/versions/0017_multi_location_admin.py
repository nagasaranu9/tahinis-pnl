"""Add location_id to users (location-scoped RBAC) and invite fields to locations.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_location_id",
        "users",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_location_id", "users", ["location_id"])

    op.add_column("locations", sa.Column("invite_email", sa.String(255), nullable=True))
    op.add_column("locations", sa.Column("invite_token_hash", sa.String(64), nullable=True))
    op.add_column(
        "locations",
        sa.Column("invite_status", sa.String(20), nullable=False, server_default="none"),
    )
    op.create_index("ix_locations_invite_token_hash", "locations", ["invite_token_hash"])


def downgrade() -> None:
    op.drop_index("ix_locations_invite_token_hash", table_name="locations")
    op.drop_column("locations", "invite_status")
    op.drop_column("locations", "invite_token_hash")
    op.drop_column("locations", "invite_email")

    op.drop_index("ix_users_location_id", table_name="users")
    op.drop_constraint("fk_users_location_id", "users", type_="foreignkey")
    op.drop_column("users", "location_id")
