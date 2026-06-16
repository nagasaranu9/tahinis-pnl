"""Google Ads adapter.

Production: wraps Google Ads API.
Mock: returns deterministic fake campaign + daily metrics for development.

Swap via GOOGLE_ADS_ADAPTER env var: "mock" (default) | "google"
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal


@dataclass
class AdsCampaignData:
    google_campaign_id: str
    google_customer_id: str
    name: str
    status: str = "ENABLED"
    campaign_type: str = "SEARCH"


@dataclass
class AdsDailyMetric:
    campaign_id: str  # google_campaign_id
    metric_date: str  # YYYY-MM-DD
    spend: Decimal = Decimal("0")
    impressions: int = 0
    clicks: int = 0
    conversions: Decimal = Decimal("0")
    roas: Decimal | None = None
    currency_code: str = "CAD"


@dataclass
class AdsData:
    campaigns: list[AdsCampaignData] = field(default_factory=list)
    daily_metrics: list[AdsDailyMetric] = field(default_factory=list)


class GoogleAdsAdapter(ABC):
    @abstractmethod
    async def fetch_data(
        self,
        customer_id: str,
        start_date: date,
        end_date: date,
    ) -> AdsData:
        """Return campaigns and daily metrics for the given customer and period."""


class MockGoogleAdsAdapter(GoogleAdsAdapter):
    """Deterministic mock for development."""

    _CAMPAIGNS = [
        ("cmp_001", "Tahinis Brand Search", "SEARCH"),
        ("cmp_002", "Tahinis Local Discovery", "PERFORMANCE_MAX"),
    ]

    async def fetch_data(
        self,
        customer_id: str,
        start_date: date,
        end_date: date,
    ) -> AdsData:
        rng = random.Random(customer_id)
        campaigns = [
            AdsCampaignData(
                google_campaign_id=cid,
                google_customer_id=customer_id,
                name=name,
                campaign_type=ctype,
            )
            for cid, name, ctype in self._CAMPAIGNS
        ]

        metrics: list[AdsDailyMetric] = []
        for campaign in campaigns:
            # Each campaign has slightly different spend profile
            base_spend = Decimal("50") if campaign.campaign_type == "SEARCH" else Decimal("80")
            current = start_date
            while current <= end_date:
                spend = (base_spend + Decimal(str(rng.uniform(-10, 20)))).quantize(Decimal("0.01"))
                impressions = rng.randint(300, 800)
                clicks = rng.randint(15, 60)
                conversions = Decimal(str(round(rng.uniform(0.5, 5.0), 2)))
                revenue = conversions * Decimal("25")  # avg order value
                roas = (revenue / spend).quantize(Decimal("0.0001")) if spend > 0 else None

                metrics.append(
                    AdsDailyMetric(
                        campaign_id=campaign.google_campaign_id,
                        metric_date=current.strftime("%Y-%m-%d"),
                        spend=max(Decimal("0"), spend),
                        impressions=impressions,
                        clicks=clicks,
                        conversions=conversions,
                        roas=roas,
                    )
                )
                current += timedelta(days=1)

        return AdsData(campaigns=campaigns, daily_metrics=metrics)


class GoogleAdsAdapterFactory:
    @staticmethod
    def create(adapter_type: str = "mock") -> GoogleAdsAdapter:
        if adapter_type == "google":
            raise NotImplementedError("Google Ads API adapter not yet implemented")
        return MockGoogleAdsAdapter()
