"""Pipeboard backfill service — chunked sync with rate limiting."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import PipeboardAccount
from app.db.repositories.pipeboard_repo import PipeboardRepository
from app.services.external_platforms.pipeboard_adapter import PipeboardAdapter, PipeboardAdapterFactory

logger = structlog.get_logger(__name__)

RATE_LIMIT_DELAY = 0.2  # seconds between API calls (conservative)


class PipeboardBackfillService:
    """Handles chunked backfill, rate limiting, metric storage."""

    def __init__(self, db: AsyncSession):
        from app.core.config import settings
        self._db = db
        self._repo = PipeboardRepository(db)
        self._adapter: PipeboardAdapter = PipeboardAdapterFactory.create(settings.PIPEBOARD_ADAPTER)

    async def sync_date_range(
        self,
        tenant_id: uuid.UUID,
        account: PipeboardAccount,
        access_token: str,
        start_date: date,
        end_date: date,
        chunk_days: int = 30,
        platform_filter: Optional[str] = None,
    ) -> int:
        """Sync date range in chunks. Returns total metrics synced."""
        total_metrics = 0

        # Split into chunks
        chunks = self._chunk_date_range(start_date, end_date, chunk_days)
        logger.info(
            "backfill_start",
            tenant_id=tenant_id,
            chunk_count=len(chunks),
            date_range=f"{start_date} to {end_date}",
        )

        for chunk_start, chunk_end in chunks:
            chunk_metrics = await self._sync_chunk(
                tenant_id=tenant_id,
                account=account,
                access_token=access_token,
                start_date=chunk_start,
                end_date=chunk_end,
                platform_filter=platform_filter,
            )
            total_metrics += chunk_metrics

            # Rate limit between chunks
            await asyncio.sleep(RATE_LIMIT_DELAY)

        return total_metrics

    async def _sync_chunk(
        self,
        tenant_id: uuid.UUID,
        account: PipeboardAccount,
        access_token: str,
        start_date: date,
        end_date: date,
        platform_filter: Optional[str],
    ) -> int:
        """Sync single date chunk. Returns metric count."""
        try:
            # Fetch campaigns (if not in filter)
            campaigns_to_process = []
            if not platform_filter:
                platforms = ["google_ads", "meta_ads", "tiktok_ads"]
            else:
                platforms = [platform_filter]

            for platform in platforms:
                try:
                    campaigns = await self._adapter.fetch_campaigns(
                        api_token=access_token,
                        pipeboard_platform=platform,
                    )

                    # Upsert campaigns
                    for camp_data in campaigns:
                        campaign = await self._repo.upsert_campaign(
                            tenant_id=tenant_id,
                            location_id=None,  # Platform doesn't map to location
                            pipeboard_platform=camp_data.pipeboard_platform,
                            pipeboard_campaign_id=camp_data.pipeboard_campaign_id,
                            name=camp_data.name,
                            status=camp_data.status,
                            campaign_type=camp_data.campaign_type,
                            daily_budget_limit=camp_data.daily_budget_limit,
                            lifetime_budget_limit=camp_data.lifetime_budget_limit,
                            spend_to_date=camp_data.spend_to_date,
                        )
                        campaigns_to_process.append(campaign)

                    await asyncio.sleep(RATE_LIMIT_DELAY)

                except Exception as e:
                    logger.error(
                        "campaign_fetch_failed",
                        platform=platform,
                        tenant_id=tenant_id,
                        error=str(e),
                    )
                    # Continue to next platform on error
                    continue

            # Fetch and store daily metrics
            metrics_count = 0
            for platform in platforms:
                try:
                    metrics_data = await self._adapter.fetch_daily_metrics(
                        api_token=access_token,
                        pipeboard_platform=platform,
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                    )

                    for metric in metrics_data:
                        # Find campaign by id
                        campaign = next(
                            (c for c in campaigns_to_process if c.pipeboard_campaign_id == metric.pipeboard_campaign_id),
                            None,
                        )
                        if not campaign:
                            # Metric for a campaign the master-list call omitted
                            # (PMax/Smart are often excluded from get_*_campaigns,
                            # and the adapter's customer-level fallback emits these).
                            # Auto-create a stub campaign so real spend isn't dropped.
                            logger.info(
                                "campaign_autocreate_from_metric",
                                campaign_id=metric.pipeboard_campaign_id,
                                platform=platform,
                            )
                            campaign = await self._repo.upsert_campaign(
                                tenant_id=tenant_id,
                                location_id=None,
                                pipeboard_platform=platform,
                                pipeboard_campaign_id=metric.pipeboard_campaign_id,
                                name=metric.pipeboard_campaign_id,
                                status="UNKNOWN",
                                campaign_type=None,
                                daily_budget_limit=None,
                                lifetime_budget_limit=None,
                                spend_to_date=None,
                            )
                            campaigns_to_process.append(campaign)

                        # Upsert metric
                        await self._repo.upsert_daily_metric(
                            tenant_id=tenant_id,
                            campaign_id=campaign.id,
                            metric_date=metric.metric_date,
                            spend=metric.spend,
                            impressions=metric.impressions,
                            clicks=metric.clicks,
                            conversions=metric.conversions,
                            conversion_value=metric.conversion_value,
                            ctr=metric.ctr,
                            cpc=metric.cpc,
                            roas=metric.roas,
                            currency_code=metric.currency_code,
                        )
                        metrics_count += 1

                    await asyncio.sleep(RATE_LIMIT_DELAY)

                except Exception as e:
                    logger.error(
                        "metrics_fetch_failed",
                        platform=platform,
                        tenant_id=tenant_id,
                        date_range=f"{start_date} to {end_date}",
                        error=str(e),
                    )
                    # Continue to next platform on error
                    continue

            await self._db.commit()
            logger.info(
                "chunk_sync_complete",
                tenant_id=tenant_id,
                date_range=f"{start_date} to {end_date}",
                metrics_synced=metrics_count,
            )
            return metrics_count

        except Exception as e:
            logger.error(
                "chunk_sync_failed",
                tenant_id=tenant_id,
                date_range=f"{start_date} to {end_date}",
                error=str(e),
            )
            raise

    @staticmethod
    def _chunk_date_range(
        start_date: date,
        end_date: date,
        chunk_days: int,
    ) -> list[tuple[date, date]]:
        """Split date range into chunks. Returns list of (chunk_start, chunk_end) tuples."""
        chunks = []
        current = start_date

        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
            chunks.append((current, chunk_end))
            current = chunk_end + timedelta(days=1)

        return chunks
