"""Repository for external platform data (Google Reviews + Ads)."""
import uuid
from decimal import Decimal

from sqlalchemy import and_, select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import (
    GoogleAdsCampaign,
    GoogleAdsDailyMetric,
    GoogleReviewSnapshot,
)
from app.services.external_platforms.google_reviews_adapter import ReviewSnapshot
from app.services.external_platforms.google_ads_adapter import AdsCampaignData, AdsDailyMetric


class ExternalPlatformRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------ reviews

    async def upsert_review_snapshot(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None,
        snapshot: ReviewSnapshot,
    ) -> None:
        stmt = (
            pg_insert(GoogleReviewSnapshot)
            .values(
                tenant_id=tenant_id,
                location_id=location_id,
                snapshot_date=snapshot.snapshot_date,
                rating_average=snapshot.rating_average,
                review_count_total=snapshot.review_count_total,
                new_reviews_count=snapshot.new_reviews_count,
                positive_count=snapshot.positive_count,
                neutral_count=snapshot.neutral_count,
                negative_count=snapshot.negative_count,
                google_place_id=snapshot.google_place_id,
            )
            .on_conflict_do_update(
                constraint="uq_review_snapshot",
                set_={
                    "rating_average": snapshot.rating_average,
                    "review_count_total": snapshot.review_count_total,
                    "new_reviews_count": snapshot.new_reviews_count,
                    "positive_count": snapshot.positive_count,
                    "neutral_count": snapshot.neutral_count,
                    "negative_count": snapshot.negative_count,
                },
            )
        )
        await self._db.execute(stmt)

    async def list_review_snapshots(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        limit: int = 90,
    ) -> tuple[list[GoogleReviewSnapshot], int]:
        conds = [GoogleReviewSnapshot.tenant_id == tenant_id]
        if location_id:
            conds.append(GoogleReviewSnapshot.location_id == location_id)
        if start_date:
            conds.append(GoogleReviewSnapshot.snapshot_date >= start_date)
        if end_date:
            conds.append(GoogleReviewSnapshot.snapshot_date <= end_date)

        total = (
            await self._db.execute(
                select(func.count()).select_from(GoogleReviewSnapshot).where(and_(*conds))
            )
        ).scalar_one()

        rows = await self._db.execute(
            select(GoogleReviewSnapshot)
            .where(and_(*conds))
            .order_by(GoogleReviewSnapshot.snapshot_date.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    # ------------------------------------------------------------------ ads

    async def upsert_campaign(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None,
        campaign: AdsCampaignData,
    ) -> GoogleAdsCampaign:
        stmt = (
            pg_insert(GoogleAdsCampaign)
            .values(
                tenant_id=tenant_id,
                location_id=location_id,
                google_campaign_id=campaign.google_campaign_id,
                google_customer_id=campaign.google_customer_id,
                name=campaign.name,
                status=campaign.status,
                campaign_type=campaign.campaign_type,
            )
            .on_conflict_do_update(
                constraint="uq_ads_campaign",
                set_={
                    "name": campaign.name,
                    "status": campaign.status,
                    "campaign_type": campaign.campaign_type,
                },
            )
            .returning(GoogleAdsCampaign)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def upsert_daily_metric(
        self,
        tenant_id: uuid.UUID,
        campaign_pk: uuid.UUID,
        metric: AdsDailyMetric,
    ) -> None:
        stmt = (
            pg_insert(GoogleAdsDailyMetric)
            .values(
                tenant_id=tenant_id,
                campaign_id=campaign_pk,
                metric_date=metric.metric_date,
                spend=metric.spend,
                impressions=metric.impressions,
                clicks=metric.clicks,
                conversions=metric.conversions,
                roas=metric.roas,
                currency_code=metric.currency_code,
            )
            .on_conflict_do_update(
                constraint="uq_ads_daily_metric",
                set_={
                    "spend": metric.spend,
                    "impressions": metric.impressions,
                    "clicks": metric.clicks,
                    "conversions": metric.conversions,
                    "roas": metric.roas,
                },
            )
        )
        await self._db.execute(stmt)

    async def list_campaigns(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
    ) -> list[GoogleAdsCampaign]:
        conds = [GoogleAdsCampaign.tenant_id == tenant_id]
        if location_id:
            conds.append(GoogleAdsCampaign.location_id == location_id)
        rows = await self._db.execute(
            select(GoogleAdsCampaign).where(and_(*conds)).order_by(GoogleAdsCampaign.name)
        )
        return list(rows.scalars().all())

    async def list_daily_metrics(
        self,
        tenant_id: uuid.UUID,
        campaign_id: uuid.UUID | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        limit: int = 90,
    ) -> tuple[list[GoogleAdsDailyMetric], int]:
        conds = [GoogleAdsDailyMetric.tenant_id == tenant_id]
        if campaign_id:
            conds.append(GoogleAdsDailyMetric.campaign_id == campaign_id)
        if start_date:
            conds.append(GoogleAdsDailyMetric.metric_date >= start_date)
        if end_date:
            conds.append(GoogleAdsDailyMetric.metric_date <= end_date)

        total = (
            await self._db.execute(
                select(func.count()).select_from(GoogleAdsDailyMetric).where(and_(*conds))
            )
        ).scalar_one()

        rows = await self._db.execute(
            select(GoogleAdsDailyMetric)
            .where(and_(*conds))
            .order_by(GoogleAdsDailyMetric.metric_date.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), total
