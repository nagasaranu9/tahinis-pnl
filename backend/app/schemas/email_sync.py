from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class EmailSyncConfigResponse(BaseModel):
    id: uuid.UUID
    provider: str
    email_address: Optional[str]
    is_active: bool
    last_synced_at: Optional[datetime]

    model_config = {"from_attributes": True}


class EmailSyncJobResponse(BaseModel):
    id: uuid.UUID
    config_id: uuid.UUID
    provider: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    messages_scanned: int
    attachments_found: int
    documents_created: int
    duplicates_skipped: int
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DriveSyncConfigResponse(BaseModel):
    id: uuid.UUID
    email_address: Optional[str]
    is_active: bool
    last_synced_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DriveSyncJobResponse(BaseModel):
    id: uuid.UUID
    config_id: uuid.UUID
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    files_scanned: int
    documents_created: int
    duplicates_skipped: int
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
