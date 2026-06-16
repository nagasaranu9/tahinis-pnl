"""AI Insight schemas."""
import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.db.models.ai_insight import INSIGHT_TYPES


class AIInsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: Optional[uuid.UUID] = None
    insight_type: str
    severity: str
    title: str
    summary: str
    explanation: str
    confidence_score: Decimal
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    document_id: Optional[uuid.UUID] = None
    expense_id: Optional[uuid.UUID] = None
    reconciliation_run_id: Optional[uuid.UUID] = None
    is_dismissed: bool
    is_helpful: Optional[bool] = None
    model_id: Optional[str] = None
    created_at: str


class GenerateInsightsRequest(BaseModel):
    insight_type: str
    period_start: str  # YYYY-MM-DD
    period_end: str  # YYYY-MM-DD
    location_id: Optional[uuid.UUID] = None

    @field_validator("insight_type")
    @classmethod
    def validate_insight_type(cls, v: str) -> str:
        if v not in INSIGHT_TYPES:
            raise ValueError(f"insight_type must be one of {INSIGHT_TYPES}")
        return v


class DismissInsightRequest(BaseModel):
    pass


class FeedbackRequest(BaseModel):
    is_helpful: bool
