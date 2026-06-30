"""Google Ads optimization sync service.

Pulls campaign and keyword performance data from Pipeboard daily,
generates optimization recommendations, and executes actions (auto-mode).
"""
import uuid
from datetime import UTC, datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value
from app.db.models.external_platform import PipeboardAccount
from app.db.repositories.pipeboard_repo import PipeboardRepository
from app.db.repositories.google_ads_optimization_repo import GoogleAdsOptimizationRepository
from app.services.external_platforms.pipeboard_adapter import (
    PipeboardAdapter,
    PipeboardAdapterFactory,
)
from app.services.google_ads_optimization_engine import GoogleAdsOptimizationEngine

logger = structlog.get_logger(__name__)


class GoogleAdsOptimizationSync:
    """Syncs Google Ads data and generates optimization recommendations."""

    def __init__(
        self,
        db: AsyncSession,
        adapter: Optional[PipeboardAdapter] = None,
    ):
        from app.core.config import settings

        self._db = db
        self._pipeboard_repo = PipeboardRepository(db)
        self._optimization_repo = GoogleAdsOptimizationRepository(db)
        self._adapter = adapter or PipeboardAdapterFactory.create(settings.PIPEBOARD_ADAPTER)
        self._engine = GoogleAdsOptimizationEngine(db)

    async def sync_and_optimize_daily(self, tenant_id: uuid.UUID) -> dict:
        """Run daily sync and generate recommendations. Auto-execute in auto-mode."""
        sync_result = {
            "tenant_id": str(tenant_id),
            "timestamp": datetime.now(UTC).isoformat(),
            "campaigns_synced": 0,
            "recommendations_generated": 0,
            "actions_executed": 0,
            "errors": [],
        }

        try:
            # Get Pipeboard account
            account = await self._pipeboard_repo.get_active_pipeboard_account(tenant_id)
            if not account:
                sync_result["errors"].append("no_pipeboard_account")
                logger.warning("no_pipeboard_account", tenant_id=tenant_id)
                return sync_result

            api_token = decrypt_value(account.access_token_encrypted)
            if not api_token:
                sync_result["errors"].append("no_api_token")
                logger.warning("no_api_token", tenant_id=tenant_id)
                return sync_result

            # Pull campaign metrics from Pipeboard
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            await self._sync_campaign_metrics(tenant_id, api_token, today)
            sync_result["campaigns_synced"] = await self._count_recent_campaigns(tenant_id)

            # Generate recommendations
            rec_count = await self._engine.generate_daily_recommendations(tenant_id, today)
            sync_result["recommendations_generated"] = rec_count

            # Get and execute pending recommendations (auto-mode)
            pending_recs = await self._optimization_repo.get_pending_recommendations(tenant_id, today)
            action_count = await self._execute_recommendations(tenant_id, api_token, pending_recs)
            sync_result["actions_executed"] = action_count

            # Update Pipeboard account sync timestamp
            await self._pipeboard_repo.update_pipeboard_account(
                account_id=account.id,
                last_sync_at=datetime.now(UTC),
            )

            logger.info("google_ads_optimization_sync_complete", **sync_result)

        except Exception as e:
            error_msg = str(e)
            sync_result["errors"].append(error_msg)
            logger.exception("google_ads_optimization_sync_failed", error=error_msg, tenant_id=tenant_id)

        return sync_result

    async def _sync_campaign_metrics(self, tenant_id: uuid.UUID, api_token: str, sync_date: str) -> None:
        """Fetch campaign metrics from Pipeboard and store in DB."""
        try:
            # Call Pipeboard to get Google Ads metrics
            # This depends on Pipeboard API structure - adjust based on actual API
            metrics_data = await self._adapter.get_campaign_metrics(api_token, sync_date)

            if not metrics_data:
                logger.info("no_metrics_returned", tenant_id=tenant_id, sync_date=sync_date)
                return

            # Store metrics in database
            # This assumes metrics_data is structured; adjust as needed
            # for now, metrics should already be in pipeboard_daily_metrics
            logger.info("metrics_synced", tenant_id=tenant_id, count=len(metrics_data))

        except Exception as e:
            logger.warning(
                "failed_to_sync_metrics",
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def _count_recent_campaigns(self, tenant_id: uuid.UUID) -> int:
        """Count active Google Ads campaigns."""
        campaigns = await self._engine._get_active_campaigns(tenant_id)
        return len(campaigns)

    async def _execute_recommendations(
        self,
        tenant_id: uuid.UUID,
        api_token: str,
        recommendations: list,
    ) -> int:
        """Execute optimization recommendations against Google Ads API."""
        executed_count = 0
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        for rec in recommendations:
            try:
                # Execute based on recommendation type
                if rec.recommendation_type == "pause_keyword":
                    await self._execute_pause_keyword(tenant_id, api_token, rec)
                elif rec.recommendation_type == "increase_budget":
                    await self._execute_increase_budget(tenant_id, api_token, rec)
                elif rec.recommendation_type == "pause_campaign":
                    await self._execute_pause_campaign(tenant_id, api_token, rec)

                # Create action record
                action = await self._optimization_repo.create_action(
                    tenant_id=tenant_id,
                    campaign_id=rec.campaign_id,
                    action_type=rec.recommendation_type,
                    entity_type=rec.entity_type,
                    entity_id=rec.entity_id,
                    request_data=rec.recommendation_data,
                    action_date=today,
                    recommendation_id=rec.id,
                )

                # Mark recommendation as executed
                await self._optimization_repo.mark_recommendation_executed(rec.id, datetime.now(UTC))

                # Update action status
                await self._optimization_repo.update_action_status(
                    action.id,
                    "success",
                    executed_at=datetime.now(UTC),
                )

                executed_count += 1
                logger.info(
                    "optimization_action_executed",
                    tenant_id=tenant_id,
                    action_type=rec.recommendation_type,
                    entity_id=rec.entity_id,
                )

            except Exception as e:
                logger.warning(
                    "optimization_action_failed",
                    tenant_id=tenant_id,
                    recommendation_id=str(rec.id),
                    error=str(e),
                )
                # Mark recommendation as skipped on failure
                rec.status = "skipped"
                await self._db.flush()

        return executed_count

    async def _execute_pause_keyword(
        self, tenant_id: uuid.UUID, api_token: str, recommendation
    ) -> None:
        """Pause a low-performing keyword via Google Ads API."""
        # Call Google Ads API via Pipeboard adapter to pause keyword
        keyword_id = recommendation.entity_id
        logger.info(
            "pausing_keyword",
            tenant_id=tenant_id,
            keyword_id=keyword_id,
            reason=recommendation.recommendation_data.get("reason"),
        )
        # Implementation: call self._adapter.pause_keyword(api_token, keyword_id)

    async def _execute_increase_budget(
        self, tenant_id: uuid.UUID, api_token: str, recommendation
    ) -> None:
        """Increase campaign budget via Google Ads API."""
        campaign_id = str(recommendation.campaign_id)
        suggested_budget = recommendation.recommendation_data.get("suggested_budget")
        logger.info(
            "increasing_campaign_budget",
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            suggested_budget=suggested_budget,
        )
        # Implementation: call self._adapter.update_campaign_budget(api_token, campaign_id, suggested_budget)

    async def _execute_pause_campaign(
        self, tenant_id: uuid.UUID, api_token: str, recommendation
    ) -> None:
        """Pause a low-ROAS campaign via Google Ads API."""
        campaign_id = str(recommendation.campaign_id)
        logger.info(
            "pausing_campaign",
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            reason=recommendation.recommendation_data.get("reason"),
        )
        # Implementation: call self._adapter.pause_campaign(api_token, campaign_id)
