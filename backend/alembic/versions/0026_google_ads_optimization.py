"""Create Google Ads optimization tables.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-30 03:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_ads_optimization_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_date", sa.String(10), nullable=False),
        sa.Column("recommendation_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("entity_name", sa.String(500)),
        sa.Column("recommendation_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("metric_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("confidence_score", sa.Numeric(precision=3, scale=2)),
        sa.Column("reasoning", sa.Text()),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["pipeboard_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "campaign_id",
            "recommendation_type",
            "entity_id",
            "entity_type",
            "recommendation_date",
            name="uq_optimization_recommendation",
        ),
    )
    op.create_index(
        "ix_google_ads_optimization_recommendations_campaign_id",
        "google_ads_optimization_recommendations",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_recommendations_entity_id",
        "google_ads_optimization_recommendations",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_recommendations_recommendation_date",
        "google_ads_optimization_recommendations",
        ["recommendation_date"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_recommendations_tenant_id",
        "google_ads_optimization_recommendations",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "google_ads_optimization_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("request_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("response_data", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("action_date", sa.String(10), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("metrics_before", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("metrics_after", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("impact_assessed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["pipeboard_campaigns.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["google_ads_optimization_recommendations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_google_ads_optimization_actions_action_date",
        "google_ads_optimization_actions",
        ["action_date"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_actions_campaign_id",
        "google_ads_optimization_actions",
        ["campaign_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_actions_entity_id",
        "google_ads_optimization_actions",
        ["entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_actions_recommendation_id",
        "google_ads_optimization_actions",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        "ix_google_ads_optimization_actions_tenant_id",
        "google_ads_optimization_actions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_google_ads_optimization_actions_tenant_id",
        table_name="google_ads_optimization_actions",
    )
    op.drop_index(
        "ix_google_ads_optimization_actions_recommendation_id",
        table_name="google_ads_optimization_actions",
    )
    op.drop_index(
        "ix_google_ads_optimization_actions_entity_id",
        table_name="google_ads_optimization_actions",
    )
    op.drop_index(
        "ix_google_ads_optimization_actions_campaign_id",
        table_name="google_ads_optimization_actions",
    )
    op.drop_index(
        "ix_google_ads_optimization_actions_action_date",
        table_name="google_ads_optimization_actions",
    )
    op.drop_table("google_ads_optimization_actions")
    op.drop_index(
        "ix_google_ads_optimization_recommendations_tenant_id",
        table_name="google_ads_optimization_recommendations",
    )
    op.drop_index(
        "ix_google_ads_optimization_recommendations_recommendation_date",
        table_name="google_ads_optimization_recommendations",
    )
    op.drop_index(
        "ix_google_ads_optimization_recommendations_entity_id",
        table_name="google_ads_optimization_recommendations",
    )
    op.drop_index(
        "ix_google_ads_optimization_recommendations_campaign_id",
        table_name="google_ads_optimization_recommendations",
    )
    op.drop_table("google_ads_optimization_recommendations")
