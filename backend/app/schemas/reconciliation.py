import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ReconciliationRunRequest(BaseModel):
    location_id: uuid.UUID | None = None
    period_start: datetime
    period_end: datetime


class ReconciliationFlagResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    run_id: uuid.UUID
    flag_type: str
    severity: str
    message: str
    document_id: uuid.UUID | None
    expense_id: uuid.UUID | None
    toast_order_id: uuid.UUID | None
    is_resolved: bool
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_note: str | None
    created_at: datetime


class ReconciliationRunResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID | None
    period_start: datetime
    period_end: datetime
    status: str
    triggered_by: uuid.UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    documents_checked: int
    expenses_checked: int
    toast_orders_checked: int
    flags_raised: int
    total_sales_amount: Decimal | None
    total_expense_amount: Decimal | None
    net_variance: Decimal | None
    created_at: datetime


class ResolveFlagRequest(BaseModel):
    resolution_note: str
