"""No-op placeholder (Toast price fix is data-only, applied via re-sync).

Originally this migration multiplied pre_discount_price/tax/discount by 100 to
undo an old ÷100 bug. That blanket UPDATE is unsafe: after the sync_service fix,
re-synced rows are already stored in correct dollars, so a ×100 pass would
corrupt them (e.g. $11.61 -> $1161). It also never touched the unit_price
column, which is what product_mix actually reads.

Correct remediation is a full Toast re-sync: the order-item upsert uses
on_conflict_do_update, so every row (unit_price, pre_discount_price, tax,
discount) is rewritten from raw Toast data via _dollars() with no ÷100. This
migration is kept as a no-op only to preserve the revision chain / single head.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-23 20:00:00.000000
"""

from alembic import op  # noqa: F401

# revision identifiers
revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op. Toast price correction is applied via full re-sync, not SQL."""
    pass


def downgrade() -> None:
    """No-op."""
    pass
