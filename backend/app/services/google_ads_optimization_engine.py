"""Google Ads optimization recommendation engine."""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import PipeboardDailyMetric, PipeboardCampaign
from app.db.repositories.google_ads_optimization_repo import GoogleAdsOptimizationRepository


class GoogleAdsOptimizationEngine:
    """Generates optimization recommendations based on campaign performance data."""

    # Thresholds for optimization rules
    LOW_CTR_THRESHOLD = Decimal("0.03")  # 3% - pause keywords below this
    HIGH_CONVERSION_THRESHOLD = 5  # Scale bids for keywords with 5+ conversions
    HIGH_ROAS_THRESHOLD = Decimal("3.0")  # Scale budget for campaigns with 3.0+ ROAS
    LOW_ROAS_THRESHOLD = Decimal("1.5")  # Pause ad groups with <1.5 ROAS
    WASTED_SPEND_THRESHOLD = Decimal("50")  # Add negatives for terms spending $50+ with 0 conversions

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = GoogleAdsOptimizationRepository(session)

    async def generate_daily_recommendations(
        self, tenant_id: uuid.UUID, recommendation_date: str
    ) -> int:
        """Generate recommendations for a specific date. Returns count of recommendations created."""
        recommendation_count = 0

        # Get all active campaigns for tenant
        campaigns = await self._get_active_campaigns(tenant_id)

        for campaign in campaigns:
            # Get metrics for last 7 days
            metrics = await self._get_campaign_metrics(campaign.id, days_back=7)

            if not metrics:
                continue

            # Apply optimization rules
            recommendations = await self._generate_campaign_recommendations(
                tenant_id, campaign, metrics, recommendation_date
            )
            recommendation_count += len(recommendations)

        return recommendation_count

    async def _get_active_campaigns(self, tenant_id: uuid.UUID) -> list[PipeboardCampaign]:
        """Get active Google Ads campaigns for tenant."""
        from sqlalchemy import select

        stmt = select(PipeboardCampaign).where(
            PipeboardCampaign.tenant_id == tenant_id,
            PipeboardCampaign.pipeboard_platform == "google_ads",
            PipeboardCampaign.status == "ENABLED",
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def _get_campaign_metrics(self, campaign_id: uuid.UUID, days_back: int = 7) -> list[dict]:
        """Get recent daily metrics for campaign."""
        from sqlalchemy import select, func
        from datetime import datetime as dt

        cutoff_date = (dt.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        stmt = select(PipeboardDailyMetric).where(
            PipeboardDailyMetric.campaign_id == campaign_id,
            PipeboardDailyMetric.metric_date >= cutoff_date,
        ).order_by(PipeboardDailyMetric.metric_date.desc())

        result = await self.session.execute(stmt)
        metrics = result.scalars().all()

        return [
            {
                "date": m.metric_date,
                "spend": m.spend,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "conversions": m.conversions or Decimal("0"),
                "ctr": m.ctr,
                "cpc": m.cpc,
                "roas": m.roas,
            }
            for m in metrics
        ]

    async def _generate_campaign_recommendations(
        self, tenant_id: uuid.UUID, campaign: PipeboardCampaign, metrics: list[dict], rec_date: str
    ) -> list[dict]:
        """Generate recommendations for a campaign."""
        recommendations = []

        if not metrics:
            return recommendations

        # Aggregate metrics over period
        total_spend = sum(Decimal(str(m.get("spend") or 0)) for m in metrics)
        total_clicks = sum(m.get("clicks") or 0 for m in metrics)
        total_conversions = sum(Decimal(str(m.get("conversions") or 0)) for m in metrics)
        total_impressions = sum(m.get("impressions") or 0 for m in metrics)

        # Calculate aggregate metrics
        avg_ctr = (
            Decimal(str(total_clicks)) / Decimal(str(total_impressions))
            if total_impressions > 0
            else Decimal("0")
        )
        avg_roas = (
            total_conversions / total_spend if total_spend > 0 else Decimal("0")
        )

        # Rule 1: Pause low-CTR keywords
        if avg_ctr < self.LOW_CTR_THRESHOLD and total_spend > self.WASTED_SPEND_THRESHOLD:
            rec = await self.repo.create_recommendation(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                recommendation_date=rec_date,
                recommendation_type="pause_keyword",
                entity_type="keyword",
                entity_id=f"campaign_{campaign.id}_low_ctr",
                entity_name=f"{campaign.name} - Low CTR",
                recommendation_data={
                    "action": "pause",
                    "reason": "low_ctr",
                    "current_ctr": float(avg_ctr),
                    "threshold": float(self.LOW_CTR_THRESHOLD),
                },
                metric_data={
                    "clicks": total_clicks,
                    "impressions": total_impressions,
                    "spend": float(total_spend),
                    "ctr": float(avg_ctr),
                },
                confidence_score=Decimal("0.85"),
                reasoning="CTR below threshold indicates low relevance. Pausing will reduce wasted spend.",
            )
            recommendations.append(rec)

        # Rule 2: Scale budget for high-ROAS campaigns
        if avg_roas >= self.HIGH_ROAS_THRESHOLD and total_conversions >= self.HIGH_CONVERSION_THRESHOLD:
            suggested_budget = (campaign.daily_budget_limit or Decimal("0")) * Decimal("1.25")
            rec = await self.repo.create_recommendation(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                recommendation_date=rec_date,
                recommendation_type="increase_budget",
                entity_type="campaign",
                entity_id=str(campaign.id),
                entity_name=campaign.name,
                recommendation_data={
                    "action": "increase_budget",
                    "reason": "high_roas",
                    "current_budget": float(campaign.daily_budget_limit or 0),
                    "suggested_budget": float(suggested_budget),
                    "increase_pct": 25,
                },
                metric_data={
                    "spend": float(total_spend),
                    "conversions": float(total_conversions),
                    "roas": float(avg_roas),
                },
                confidence_score=Decimal("0.90"),
                reasoning="High ROAS indicates strong performance. Increasing budget will capture more conversions.",
            )
            recommendations.append(rec)

        # Rule 3: Pause low-performing campaigns
        if avg_roas < self.LOW_ROAS_THRESHOLD and total_spend > self.WASTED_SPEND_THRESHOLD:
            rec = await self.repo.create_recommendation(
                tenant_id=tenant_id,
                campaign_id=campaign.id,
                recommendation_date=rec_date,
                recommendation_type="pause_campaign",
                entity_type="campaign",
                entity_id=str(campaign.id),
                entity_name=campaign.name,
                recommendation_data={
                    "action": "pause",
                    "reason": "low_roas",
                    "current_roas": float(avg_roas),
                    "threshold": float(self.LOW_ROAS_THRESHOLD),
                },
                metric_data={
                    "spend": float(total_spend),
                    "conversions": float(total_conversions),
                    "roas": float(avg_roas),
                },
                confidence_score=Decimal("0.75"),
                reasoning="ROAS below threshold indicates poor performance. Pausing until optimization complete.",
            )
            recommendations.append(rec)

        return recommendations
