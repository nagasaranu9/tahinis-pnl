"""Fix Toast order item prices: undo old ÷100 bug by multiplying by 100.

Old code incorrectly applied cents_to_decimal (÷100) to selection price fields
that were already in dollars. Multiply stored pre_discount_price, tax_amount,
discount_amount by 100 to restore original values.

Revision ID: 0024_fix_toast_item_prices_undo_divide_100
Revises: 0023_pipeboard_alerts_audit_logs
Create Date: 2026-06-23 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0024_fix_toast_item_prices_undo_divide_100"
down_revision = None  # Standalone migration - doesn't depend on prior migrations
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Multiply pre_discount_price, tax_amount, discount_amount by 100."""
    # Check if table exists before attempting update (defensive)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'toast_order_item' not in inspector.get_table_names():
        return

    op.execute("""
        UPDATE toast_order_item
        SET
            pre_discount_price = pre_discount_price * 100,
            tax_amount = COALESCE(tax_amount * 100, NULL),
            discount_amount = COALESCE(discount_amount * 100, NULL)
        WHERE tenant_id IS NOT NULL;
    """)


def downgrade() -> None:
    """Divide by 100 to revert (use only if rolling back)."""
    op.execute("""
        UPDATE toast_order_item
        SET
            pre_discount_price = pre_discount_price / 100,
            tax_amount = COALESCE(tax_amount / 100, NULL),
            discount_amount = COALESCE(discount_amount / 100, NULL)
        WHERE tenant_id IS NOT NULL;
    """)
