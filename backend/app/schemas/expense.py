import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.db.models.expense import EXPENSE_CATEGORIES


class ExpenseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID | None
    document_id: uuid.UUID | None
    vendor_name: str | None
    amount: Decimal | None
    currency_code: str
    expense_date: datetime
    category: str | None
    ai_suggested_category: str | None
    ai_confidence_score: Decimal | None
    ai_explanation: str | None
    is_ai_categorized: bool
    user_overridden: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ExpenseCategoryOverrideRequest(BaseModel):
    category: str

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in EXPENSE_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {sorted(EXPENSE_CATEGORIES)}")
        return v


class ExpenseListFilter(BaseModel):
    location_id: uuid.UUID | None = None
    category: str | None = None
    vendor_name: str | None = None
    uncategorized_only: bool = False
    page: int = 1
    limit: int = 50
