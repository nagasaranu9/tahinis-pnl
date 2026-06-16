"""toast integration

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-11

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "toast_sync_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_credential_id", UUID(as_uuid=True), sa.ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True),
        sa.Column("toast_restaurant_guid", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("historical_import_complete", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("historical_import_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "location_id", name="uq_toast_sync_config_location"),
    )
    op.create_index("ix_toast_sync_configs_tenant_id", "toast_sync_configs", ["tenant_id"])
    op.create_index("ix_toast_sync_configs_location_id", "toast_sync_configs", ["location_id"])

    op.execute("""
        CREATE TRIGGER update_toast_sync_configs_updated_at
        BEFORE UPDATE ON toast_sync_configs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_sync_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("date_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orders_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("employees_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_entries_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_toast_sync_jobs_tenant_id", "toast_sync_jobs", ["tenant_id"])
    op.create_index("ix_toast_sync_jobs_location_id", "toast_sync_jobs", ["location_id"])
    op.create_index("ix_toast_sync_jobs_status", "toast_sync_jobs", ["status"])
    op.execute("""
        CREATE TRIGGER update_toast_sync_jobs_updated_at
        BEFORE UPDATE ON toast_sync_jobs
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("toast_restaurant_guid", sa.String(255), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.String(10), nullable=True),
        sa.Column("display_number", sa.String(50), nullable=True),
        sa.Column("order_source", sa.String(100), nullable=True),
        sa.Column("dining_option", sa.String(100), nullable=True),
        sa.Column("table_name", sa.String(100), nullable=True),
        sa.Column("server_guid", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tip_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("refund_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("void_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("guest_count", sa.Integer(), nullable=True),
        sa.Column("raw_data", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_order_guid"),
    )
    op.create_index("ix_toast_orders_tenant_id", "toast_orders", ["tenant_id"])
    op.create_index("ix_toast_orders_location_id", "toast_orders", ["location_id"])
    op.create_index("ix_toast_orders_business_date", "toast_orders", ["business_date"])
    op.create_index("ix_toast_orders_closed_at", "toast_orders", ["closed_at"])
    op.execute("""
        CREATE TRIGGER update_toast_orders_updated_at
        BEFORE UPDATE ON toast_orders
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_order_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("toast_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("menu_item_guid", sa.String(255), nullable=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=True),
        sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("pre_discount_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("void_reason", sa.String(255), nullable=True),
        sa.Column("is_void", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_order_item_guid"),
    )
    op.create_index("ix_toast_order_items_tenant_id", "toast_order_items", ["tenant_id"])
    op.create_index("ix_toast_order_items_order_id", "toast_order_items", ["order_id"])
    op.execute("""
        CREATE TRIGGER update_toast_order_items_updated_at
        BEFORE UPDATE ON toast_order_items
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", UUID(as_uuid=True), sa.ForeignKey("toast_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("payment_type", sa.String(100), nullable=True),
        sa.Column("card_type", sa.String(100), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tip_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("refund_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_refund", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_payment_guid"),
    )
    op.create_index("ix_toast_payments_tenant_id", "toast_payments", ["tenant_id"])
    op.create_index("ix_toast_payments_order_id", "toast_payments", ["order_id"])
    op.execute("""
        CREATE TRIGGER update_toast_payments_updated_at
        BEFORE UPDATE ON toast_payments
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_employees",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("job_codes", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_employee_guid"),
    )
    op.create_index("ix_toast_employees_tenant_id", "toast_employees", ["tenant_id"])
    op.create_index("ix_toast_employees_location_id", "toast_employees", ["location_id"])
    op.execute("""
        CREATE TRIGGER update_toast_employees_updated_at
        BEFORE UPDATE ON toast_employees
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_time_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", UUID(as_uuid=True), sa.ForeignKey("toast_employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("in_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("out_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.String(10), nullable=True),
        sa.Column("job_code", sa.String(255), nullable=True),
        sa.Column("hours_regular", sa.Numeric(10, 4), nullable=True),
        sa.Column("hours_overtime", sa.Numeric(10, 4), nullable=True),
        sa.Column("declared_cash_tips", sa.Numeric(15, 2), nullable=True),
        sa.Column("non_cash_tips", sa.Numeric(15, 2), nullable=True),
        sa.Column("hourly_wage", sa.Numeric(15, 4), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("auto_clocked_out", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_time_entry_guid"),
    )
    op.create_index("ix_toast_time_entries_tenant_id", "toast_time_entries", ["tenant_id"])
    op.create_index("ix_toast_time_entries_employee_id", "toast_time_entries", ["employee_id"])
    op.create_index("ix_toast_time_entries_business_date", "toast_time_entries", ["business_date"])
    op.execute("""
        CREATE TRIGGER update_toast_time_entries_updated_at
        BEFORE UPDATE ON toast_time_entries
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_menus",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_menu_guid"),
    )
    op.create_index("ix_toast_menus_tenant_id", "toast_menus", ["tenant_id"])
    op.execute("""
        CREATE TRIGGER update_toast_menus_updated_at
        BEFORE UPDATE ON toast_menus
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    op.create_table(
        "toast_menu_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("menu_id", UUID(as_uuid=True), sa.ForeignKey("toast_menus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("toast_guid", sa.String(255), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("plu", sa.String(255), nullable=True),
        sa.Column("price", sa.Numeric(15, 2), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("currency_code", sa.String(3), nullable=False, server_default="CAD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "toast_guid", name="uq_toast_menu_item_guid"),
    )
    op.create_index("ix_toast_menu_items_tenant_id", "toast_menu_items", ["tenant_id"])
    op.create_index("ix_toast_menu_items_menu_id", "toast_menu_items", ["menu_id"])
    op.execute("""
        CREATE TRIGGER update_toast_menu_items_updated_at
        BEFORE UPDATE ON toast_menu_items
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    for table in [
        "toast_menu_items",
        "toast_menus",
        "toast_time_entries",
        "toast_employees",
        "toast_payments",
        "toast_order_items",
        "toast_orders",
        "toast_sync_jobs",
        "toast_sync_configs",
    ]:
        op.drop_table(table)
