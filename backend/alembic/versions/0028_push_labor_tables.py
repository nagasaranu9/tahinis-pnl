"""PushOperations labor tables

Adds employee-grain daily labor cost pulled from the PushOperations API, plus
sync config and job-history tables mirroring the Toast integration pattern.

Revision ID: 0028
Revises: 0027
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_labour_employee_daily",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("push_company_id", sa.Integer(), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=True),
        # NOT NULL because it is part of uq_push_labour_employee_daily and
        # Postgres treats NULLs as distinct, which would defeat the upsert.
        sa.Column("position_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("position_name", sa.String(255), nullable=True),
        sa.Column("labour_type", sa.String(20), nullable=False),
        sa.Column("cost", sa.Numeric(15, 2), nullable=False),
        sa.Column("hours", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_labour_employee_daily_tenant_id", "push_labour_employee_daily", ["tenant_id"])
    op.create_index("ix_push_labour_employee_daily_location_id", "push_labour_employee_daily", ["location_id"])
    op.create_index("ix_push_labour_employee_daily_business_date", "push_labour_employee_daily", ["business_date"])
    # Natural key for idempotent upsert: re-syncing a date corrects rows in
    # place instead of duplicating them (Push allows retroactive punch edits).
    op.create_unique_constraint(
        "uq_push_labour_employee_daily",
        "push_labour_employee_daily",
        ["tenant_id", "push_company_id", "business_date", "employee_id", "position_id", "labour_type"],
    )
    # Covering index for the P&L labor aggregate: SUM(cost) over a date range
    # scoped to one tenant.
    op.create_index(
        "ix_push_labour_tenant_date",
        "push_labour_employee_daily",
        ["tenant_id", "business_date"],
    )

    op.create_table(
        "push_sync_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "location_id",
            UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("push_company_id", sa.Integer(), nullable=False),
        sa.Column("push_company_uuid", sa.String(64), nullable=True),
        sa.Column("push_company_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("historical_import_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("historical_import_from", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_sync_configs_tenant_id", "push_sync_configs", ["tenant_id"])
    op.create_unique_constraint(
        "uq_push_sync_config_company", "push_sync_configs", ["tenant_id", "push_company_id"]
    )

    op.create_table(
        "push_sync_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("push_company_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_sync_jobs_tenant_id", "push_sync_jobs", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("push_sync_jobs")
    op.drop_table("push_sync_configs")
    op.drop_table("push_labour_employee_daily")
