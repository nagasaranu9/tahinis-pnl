"""Schemas for external platform data (Google Reviews, Google Ads)."""
import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GoogleReviewSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    snapshot_date: str
    rating_average: Optional[Decimal] = None
    review_count_total: int
    new_reviews_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    google_place_id: Optional[str] = None
    created_at: str


class GoogleAdsCampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    google_campaign_id: str
    google_customer_id: str
    name: str
    status: str
    campaign_type: Optional[str] = None


class GoogleAdsDailyMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    campaign_id: uuid.UUID
    metric_date: str
    spend: Optional[Decimal] = None
    impressions: int
    clicks: int
    conversions: Optional[Decimal] = None
    roas: Optional[Decimal] = None
    currency_code: str


class GoogleAdsSummaryResponse(BaseModel):
    """Aggregated ads metrics across all campaigns for a period."""

    period_start: str
    period_end: str
    total_spend: Decimal
    total_impressions: int
    total_clicks: int
    total_conversions: Decimal
    average_roas: Optional[Decimal] = None
    campaigns: list[GoogleAdsCampaignResponse] = []
    daily_metrics: list[GoogleAdsDailyMetricResponse] = []
