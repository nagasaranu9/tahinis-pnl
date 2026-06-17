"""Google Reviews: configs, reviews, daily snapshots.

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    try:
        op.create_table(
            "google_review_configs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("place_id", sa.String(255), nullable=False),
            sa.Column("account_name", sa.String(500)),
            sa.Column("location_name", sa.String(500)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("last_synced_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "location_id", name="uq_google_review_config_location"),
        )
        op.create_index("ix_google_review_configs_tenant_id", "google_review_configs", ["tenant_id"])
    except Exception:
        pass

    try:
        op.create_table(
            "google_reviews",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("review_id", sa.String(500), nullable=False),
            sa.Column("author_name", sa.String(255)),
            sa.Column("rating", sa.Integer),
            sa.Column("comment", sa.Text),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("update_time", sa.DateTime(timezone=True)),
            sa.Column("reply_comment", sa.Text),
            sa.Column("reply_update_time", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "review_id", name="uq_google_review_tenant"),
        )
        op.create_index("ix_google_reviews_tenant_id", "google_reviews", ["tenant_id"])
        op.create_index("ix_google_reviews_location_id", "google_reviews", ["location_id"])
        op.create_index("ix_google_reviews_published_at", "google_reviews", ["published_at"])
    except Exception:
        pass

    try:
        op.create_table(
            "google_review_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("average_rating", sa.Numeric(3, 2)),
            sa.Column("total_review_count", sa.Integer),
            sa.Column("five_star_count", sa.Integer),
            sa.Column("four_star_count", sa.Integer),
            sa.Column("three_star_count", sa.Integer),
            sa.Column("two_star_count", sa.Integer),
            sa.Column("one_star_count", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "location_id", "snapshot_date", name="uq_review_snapshot_day"),
        )
        op.create_index("ix_google_review_snapshots_tenant_id", "google_review_snapshots", ["tenant_id"])
    except Exception:
        pass


def downgrade() -> None:
    op.drop_table("google_review_snapshots")
    op.drop_table("google_reviews")
    op.drop_table("google_review_configs")
