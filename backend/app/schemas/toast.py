from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator


class ToastConnectRequest(BaseModel):
    location_id: uuid.UUID
    client_id: str
    client_secret: str
    toast_restaurant_guid: str
    historical_import_from: Optional[datetime] = None


class ToastConnectResponse(BaseModel):
    location_id: uuid.UUID
    toast_restaurant_guid: str
    is_active: bool
    historical_import_complete: bool
    last_synced_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ToastSyncJobResponse(BaseModel):
    id: uuid.UUID
    location_id: uuid.UUID
    job_type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    date_from: Optional[datetime]
    date_to: Optional[datetime]
    orders_synced: int
    employees_synced: int
    time_entries_synced: int
    error_message: Optional[str]
    triggered_by: Optional[uuid.UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class ManualSyncRequest(BaseModel):
    location_id: uuid.UUID
    sync_type: str = "incremental"  # incremental | historical
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
