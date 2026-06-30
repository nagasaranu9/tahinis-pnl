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

            # Optimization reads pipeboard_daily_metrics, refreshed by the daily
            # Pipeboard sync (07:30 UTC) — this job runs 08:30 UTC on fresh data.
            today = datetime.now(UTC).strftime("%Y-%m-%d")
            sync_result["campaigns_synced"] = await self._count_recent_campaigns(tenant_id)

            # Generate recommendations
            rec_count = await self._engine.generate_daily_recommendations(tenant_id, today)
            sync_result["recommendations_generated"] = rec_count

            # Resolve Google Ads customer id (single account per tenant).
            customer_id = await self._resolve_customer_id(api_token)

            # Get and execute pending recommendations (auto-mode)
            pending_recs = await self._optimization_repo.get_pending_recommendations(tenant_id, today)
            action_count = await self._execute_recommendations(
                tenant_id, api_token, customer_id, pending_recs
            )
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

    async def _count_recent_campaigns(self, tenant_id: uuid.UUID) -> int:
        """Count active Google Ads campaigns."""
        campaigns = await self._engine._get_active_campaigns(tenant_id)
        return len(campaigns)

    async def _resolve_customer_id(self, api_token: str) -> str:
        """Resolve the Google Ads customer id (first account on token)."""
        accounts = await self._adapter.list_accounts(api_token, "google_ads")
        if not accounts:
            raise ValueError("no_google_ads_accounts")
        return str(accounts[0].get("id") or accounts[0].get("customer_id") or "")

    async def _get_google_campaign_id(self, campaign_id: uuid.UUID) -> str:
        """Map internal campaign uuid -> pipeboard/google campaign id."""
        from app.db.models.external_platform import PipeboardCampaign

        campaign = await self._db.get(PipeboardCampaign, campaign_id)
        if not campaign:
            raise ValueError(f"campaign_not_found:{campaign_id}")
        return campaign.pipeboard_campaign_id

    async def _execute_recommendations(
        self,
        tenant_id: uuid.UUID,
        api_token: str,
        customer_id: str,
        recommendations: list,
    ) -> int:
        """Execute optimization recommendations against Google Ads API."""
        executed_count = 0
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        for rec in recommendations:
            # Create action record (pending) before the call for audit trail.
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

            try:
                response = await self._dispatch_action(api_token, customer_id, rec)

                await self._optimization_repo.mark_recommendation_executed(rec.id, datetime.now(UTC))
                await self._optimization_repo.update_action_status(
                    action.id,
                    "success",
                    response_data=response if isinstance(response, dict) else {"raw": str(response)},
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
                await self._optimization_repo.update_action_status(
                    action.id,
                    "failed",
                    error_message=str(e),
                )
                rec.status = "skipped"
                await self._db.flush()

        return executed_count

    async def _dispatch_action(
        self, api_token: str, customer_id: str, rec
    ) -> dict:
        """Route a recommendation to the correct adapter mutation."""
        rec_type = rec.recommendation_type
        data = rec.recommendation_data or {}

        if rec_type == "pause_campaign":
            google_id = await self._get_google_campaign_id(rec.campaign_id)
            return await self._adapter.pause_campaign(api_token, customer_id, google_id)

        if rec_type == "increase_budget":
            google_id = await self._get_google_campaign_id(rec.campaign_id)
            budget = float(data.get("suggested_budget") or 0)
            return await self._adapter.update_campaign_budget(
                api_token, customer_id, google_id, budget
            )

        if rec_type == "pause_keyword":
            # entity_id encodes ad_group:criterion when available, else campaign sentinel.
            parts = str(rec.entity_id).split(":")
            if len(parts) == 2:
                return await self._adapter.pause_keyword(api_token, customer_id, parts[0], parts[1])
            # Sentinel (campaign-level low CTR) -> add negative instead of pausing a real id.
            google_id = await self._get_google_campaign_id(rec.campaign_id)
            term = data.get("keyword_text") or rec.entity_name or "low_ctr_placeholder"
            return await self._adapter.add_negative_keyword(api_token, customer_id, google_id, term)

        if rec_type == "add_negative":
            google_id = await self._get_google_campaign_id(rec.campaign_id)
            return await self._adapter.add_negative_keyword(
                api_token, customer_id, google_id,
                data.get("keyword_text", ""), data.get("match_type", "EXACT"),
            )

        raise ValueError(f"unknown_recommendation_type:{rec_type}")
