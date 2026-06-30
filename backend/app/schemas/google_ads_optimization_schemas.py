"""Schemas for Google Ads optimization API."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class RecommendationResponse(BaseModel):
    id: str
    campaign_id: str
    recommendation_date: str
    recommendation_type: str
    status: str
    entity_type: str
    entity_id: str
    entity_name: Optional[str] = None
    recommendation_data: dict
    metric_data: dict
    confidence_score: Optional[float] = None
    reasoning: Optional[str] = None
    executed_at: Optional[datetime] = None
    created_at: datetime


class ActionResponse(BaseModel):
    id: str
    campaign_id: str
    recommendation_id: Optional[str] = None
    action_type: str
    entity_type: str
    entity_id: str
    status: str
    error_message: Optional[str] = None
    request_data: dict
    response_data: Optional[dict] = None
    action_date: str
    executed_at: Optional[datetime] = None
    created_at: datetime


class OptimizationRunResponse(BaseModel):
    tenant_id: str
    timestamp: str
    campaigns_synced: int
    recommendations_generated: int
    actions_executed: int
    errors: list[str]


class OptimizationSummaryResponse(BaseModel):
    """Aggregate stats for the dashboard tile."""
    total_recommendations: int
    total_actions: int
    actions_succeeded: int
    actions_failed: int
    last_run_at: Optional[str] = None
    status: str  # healthy / watch / alert
