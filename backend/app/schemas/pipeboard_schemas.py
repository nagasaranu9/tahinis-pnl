"""Pipeboard request/response schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OAuthCallbackRequest(BaseModel):
    """OAuth callback payload."""

    code: str = Field(..., description="Authorization code from Pipeboard")
    state: str = Field(..., description="State param for CSRF validation")


class OAuthCallbackResponse(BaseModel):
    """OAuth callback response."""

    success: bool
    account_id: str
    message: str


class PipeboardAccountStatus(BaseModel):
    """Account connection status."""

    connected: bool
    account_id: Optional[str] = None
    is_active: bool
    last_sync_at: Optional[str] = None
    last_sync_error: Optional[str] = None
    pipeboard_account_id: Optional[str] = None


class CategoryMappingRequest(BaseModel):
    """Create/update category mapping."""

    pipeboard_platform: str = Field(..., description="google_ads / meta_ads / tiktok_ads")
    pipeboard_campaign_type: Optional[str] = Field(None, description="SEARCH / DISPLAY / null = any")
    expense_category: str = Field(..., description="Expense category")


class CategoryMappingResponse(BaseModel):
    """Category mapping response."""

    id: str
    pipeboard_platform: str
    pipeboard_campaign_type: Optional[str]
    expense_category: str
    created_at: datetime
    updated_at: datetime


class CampaignData(BaseModel):
    """Campaign record."""

    id: str
    pipeboard_platform: str
    pipeboard_campaign_id: str
    name: str
    status: str
    campaign_type: Optional[str]
    daily_budget_limit: Optional[Decimal]
    lifetime_budget_limit: Optional[Decimal]
    spend_to_date: Optional[Decimal]
    created_at: datetime
    updated_at: datetime


class DailyMetricData(BaseModel):
    """Daily metric record."""

    id: str
    campaign_id: str
    metric_date: str
    spend: Decimal
    impressions: int
    clicks: int
    conversions: Optional[Decimal]
    conversion_value: Optional[Decimal]
    ctr: Optional[Decimal]
    cpc: Optional[Decimal]
    roas: Optional[Decimal]
    currency_code: str
    created_at: datetime


class SyncJobResponse(BaseModel):
    """Sync job status."""

    id: str
    job_type: str
    status: str  # pending / running / complete / failed
    pipeboard_platform: Optional[str]
    date_from: Optional[str]
    date_to: Optional[str]
    metrics_synced: int
    campaigns_synced: int
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    triggered_by: Optional[str]


class ManualSyncRequest(BaseModel):
    """Request manual sync."""

    date_from: Optional[str] = Field(None, description="YYYY-MM-DD, defaults to today")
    date_to: Optional[str] = Field(None, description="YYYY-MM-DD, defaults to today")
    pipeboard_platform: Optional[str] = Field(None, description="google_ads / meta_ads / tiktok_ads, null = all")


class DisconnectRequest(BaseModel):
    """Request disconnect."""

    confirm: bool = Field(..., description="Must be true to confirm disconnect")


class AlertResponse(BaseModel):
    """Dashboard alert."""

    id: str
    alert_type: str
    severity: str  # info / warning / error / critical
    title: str
    message: str
    is_dismissed: bool
    created_at: datetime


class AuditLogResponse(BaseModel):
    """Audit log entry."""

    id: str
    event_type: str
    severity: str
    message: str
    error_detail: Optional[str]
    account_id: Optional[str]
    created_at: datetime


class DismissAlertRequest(BaseModel):
    """Request to dismiss an alert."""

    alert_id: str
