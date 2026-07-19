"""Google review config last_sync_error column

Records the failure reason when a GBP reviews sync page-fetch errors, so a
sync that silently imported 0 rows (e.g. Reviews v4 API not yet enabled)
shows up as failed instead of looking "Active" with stale last_synced_at.

Revision ID: 0030
Revises: 0029
"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("google_review_configs", sa.Column("last_sync_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("google_review_configs", "last_sync_error")
