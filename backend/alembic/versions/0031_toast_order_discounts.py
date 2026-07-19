"""Named Toast order discounts

Toast's appliedDiscounts carry the promo name (staff comp, delivery-marketplace
promo, student discount, …) but only the summed amount was stored on the order.
This table keeps per-discount detail so discounting can be attributed to a
channel, promo, or comp type.

Revision ID: 0031
Revises: 0030
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "toast_order_discounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("toast_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("discount_type", sa.String(100), nullable=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="check"),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_order_discount_guid"),
    )
    op.create_index("ix_toast_order_discounts_tenant_id", "toast_order_discounts", ["tenant_id"])
    op.create_index("ix_toast_order_discounts_business_date", "toast_order_discounts", ["business_date"])
    op.create_index("ix_toast_order_discounts_name", "toast_order_discounts", ["name"])


def downgrade() -> None:
    op.drop_index("ix_toast_order_discounts_name", table_name="toast_order_discounts")
    op.drop_index("ix_toast_order_discounts_business_date", table_name="toast_order_discounts")
    op.drop_index("ix_toast_order_discounts_tenant_id", table_name="toast_order_discounts")
    op.drop_table("toast_order_discounts")
