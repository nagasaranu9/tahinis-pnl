import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    location_id: uuid.UUID | None
    source: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    status: str
    document_type: str
    document_date: datetime | None
    vendor_name: str | None
    total_amount: Decimal | None
    currency_code: str
    is_duplicate: bool
    duplicate_of: uuid.UUID | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    download_url: str | None = None

    model_config = {"from_attributes": True}


class OCRResultResponse(BaseModel):
    id: uuid.UUID
    provider: str
    extracted_text: str
    confidence_score: Decimal
    page_count: int
    processing_time_ms: int | None
    processed_at: datetime

    model_config = {"from_attributes": True}


class LineItemResponse(BaseModel):
    id: uuid.UUID
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal
    currency_code: str
    confidence_score: Decimal
    manually_corrected: bool

    model_config = {"from_attributes": True}


class LineItemCorrectionRequest(BaseModel):
    description: str | None = None
    amount: Decimal | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
