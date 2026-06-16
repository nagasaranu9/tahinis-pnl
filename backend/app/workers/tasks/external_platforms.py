"""External platform sync Celery tasks.

sync_google_reviews  — daily, per-tenant.
sync_google_ads      — daily, per-tenant.
daily_external_sync_all_tenants — Beat entry.
"""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import structlog

from app.core.config import settings
from app.db.session import get_db_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="external.sync_google_reviews", bind=True, max_retries=3, default_retry_delay=300)
def sync_google_reviews(
    self,
    tenant_id: str,
    place_id: str,
    location_id: str | None = None,
    days_back: int = 7,
) -> None:
    asyncio.run(_sync_reviews(tenant_id, place_id, location_id, days_back))


async def _sync_reviews(
    tenant_id: str,
    place_id: str,
    location_id: str | None,
    days_back: int,
) -> None:
    from app.services.external_platforms.google_reviews_adapter import GoogleReviewsAdapterFactory
    from app.db.repositories.external_platform_repo import ExternalPlatformRepository

    adapter_type = getattr(settings, "GOOGLE_REVIEWS_ADAPTER", "mock")
    adapter = GoogleReviewsAdapterFactory.create(adapter_type)

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back - 1)

    snapshots = await adapter.fetch_snapshots(place_id, start_date, end_date)

    async with get_db_context() as db:
        repo = ExternalPlatformRepository(db)
        for snapshot in snapshots:
            await repo.upsert_review_snapshot(
                tenant_id=uuid.UUID(tenant_id),
                location_id=uuid.UUID(location_id) if location_id else None,
                snapshot=snapshot,
            )
        await db.commit()

    logger.info(
        "google_reviews_synced",
        tenant_id=tenant_id,
        count=len(snapshots),
        start=str(start_date),
    )


@celery_app.task(name="external.sync_google_ads", bind=True, max_retries=3, default_retry_delay=300)
def sync_google_ads(
    self,
    tenant_id: str,
    customer_id: str,
    location_id: str | None = None,
    days_back: int = 7,
) -> None:
    asyncio.run(_sync_ads(tenant_id, customer_id, location_id, days_back))


async def _sync_ads(
    tenant_id: str,
    customer_id: str,
    location_id: str | None,
    days_back: int,
) -> None:
    from app.services.external_platforms.google_ads_adapter import GoogleAdsAdapterFactory
    from app.db.repositories.external_platform_repo import ExternalPlatformRepository

    adapter_type = getattr(settings, "GOOGLE_ADS_ADAPTER", "mock")
    adapter = GoogleAdsAdapterFactory.create(adapter_type)

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back - 1)

    ads_data = await adapter.fetch_data(customer_id, start_date, end_date)

    async with get_db_context() as db:
        repo = ExternalPlatformRepository(db)
        t_id = uuid.UUID(tenant_id)
        loc_id = uuid.UUID(location_id) if location_id else None

        # Upsert campaigns; build google_campaign_id → db pk map
        campaign_pk_map: dict[str, uuid.UUID] = {}
        for campaign in ads_data.campaigns:
            db_campaign = await repo.upsert_campaign(t_id, loc_id, campaign)
            campaign_pk_map[campaign.google_campaign_id] = db_campaign.id

        # Upsert daily metrics
        for metric in ads_data.daily_metrics:
            campaign_pk = campaign_pk_map.get(metric.campaign_id)
            if campaign_pk:
                await repo.upsert_daily_metric(t_id, campaign_pk, metric)

        await db.commit()

    logger.info(
        "google_ads_synced",
        tenant_id=tenant_id,
        campaigns=len(ads_data.campaigns),
        metrics=len(ads_data.daily_metrics),
    )


@celery_app.task(name="external.daily_external_sync_all_tenants")
def daily_external_sync_all_tenants() -> None:
    """Celery Beat entry — daily sync for all tenants (mock adapters only, real credentials TBD)."""
    asyncio.run(_daily_all())


async def _daily_all() -> None:
    from sqlalchemy import select
    from app.db.models.tenant import Tenant

    async with get_db_context() as db:
        rows = await db.execute(select(Tenant))
        tenants = rows.scalars().all()

    for tenant in tenants:
        # Use placeholder IDs — real integrations will store place_id/customer_id in credentials
        sync_google_reviews.apply_async(
            kwargs={
                "tenant_id": str(tenant.id),
                "place_id": f"mock_place_{tenant.id.hex[:8]}",
                "days_back": 7,
            },
            queue="sync",
        )
        sync_google_ads.apply_async(
            kwargs={
                "tenant_id": str(tenant.id),
                "customer_id": f"mock_cust_{tenant.id.hex[:8]}",
                "days_back": 7,
            },
            queue="sync",
        )

    logger.info("daily_external_sync_dispatched", tenants=len(tenants))
