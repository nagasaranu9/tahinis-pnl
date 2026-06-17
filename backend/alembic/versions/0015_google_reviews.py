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
    op.execute("""
        CREATE TABLE IF NOT EXISTS google_review_configs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            location_id UUID NOT NULL,
            place_id VARCHAR(255) NOT NULL,
            account_name VARCHAR(500),
            location_name VARCHAR(500),
            is_active BOOLEAN NOT NULL DEFAULT true,
            last_synced_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_google_review_config_location UNIQUE (tenant_id, location_id),
            CONSTRAINT fk_google_review_configs_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_google_review_configs_tenant_id ON google_review_configs(tenant_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS google_reviews (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            location_id UUID NOT NULL,
            review_id VARCHAR(500) NOT NULL,
            author_name VARCHAR(255),
            rating INTEGER,
            comment TEXT,
            published_at TIMESTAMPTZ,
            update_time TIMESTAMPTZ,
            reply_comment TEXT,
            reply_update_time TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_google_review_tenant UNIQUE (tenant_id, review_id),
            CONSTRAINT fk_google_reviews_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_google_reviews_tenant_id ON google_reviews(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_google_reviews_location_id ON google_reviews(location_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_google_reviews_published_at ON google_reviews(published_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS google_review_snapshots (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL,
            location_id UUID NOT NULL,
            snapshot_date TIMESTAMPTZ NOT NULL,
            average_rating NUMERIC(3, 2),
            total_review_count INTEGER,
            five_star_count INTEGER,
            four_star_count INTEGER,
            three_star_count INTEGER,
            two_star_count INTEGER,
            one_star_count INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_review_snapshot_day UNIQUE (tenant_id, location_id, snapshot_date),
            CONSTRAINT fk_google_review_snapshots_location_id FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE CASCADE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_google_review_snapshots_tenant_id ON google_review_snapshots(tenant_id)")


def downgrade() -> None:
    op.drop_table("google_review_snapshots")
    op.drop_table("google_reviews")
    op.drop_table("google_review_configs")
