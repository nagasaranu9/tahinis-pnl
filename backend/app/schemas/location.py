import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, EmailStr, field_validator


class LocationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    address: str | None
    timezone: str
    toast_location_id: str | None
    store_id: str | None
    is_active: bool
    uber_eats_id: str | None = None
    skip_the_dishes_id: str | None = None
    doordash_id: str | None = None
    google_place_id: str | None = None
    business_hours: dict[str, Any] | None = None
    rent_monthly_incl_hst: Decimal | None = None
    contacts: dict[str, Any] | None = None
    invite_email: str | None = None
    invite_status: str = "none"
    onboarding_completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class OnboardingStepStatus(BaseModel):
    profile: bool
    toast: bool
    gmail: bool
    google: bool


class OnboardingStatusResponse(BaseModel):
    location_id: uuid.UUID
    steps: OnboardingStepStatus
    completed: bool
    completed_at: datetime | None = None


class InviteLocationOwnerRequest(BaseModel):
    store_id: str
    name: str
    invite_email: EmailStr

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, v: str) -> str:
        if not v.isdigit() or not (4 <= len(v) <= 5):
            raise ValueError("Store ID must be 4-5 digits")
        return v


class AcceptInviteRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_len(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class InviteLocationOwnerResponse(BaseModel):
    location: LocationResponse
    invite_url: str
    email_sent: bool = False


class CreateLocationRequest(BaseModel):
    name: str
    address: str | None = None
    timezone: str = "UTC"
    toast_location_id: str | None = None
    store_id: str | None = None
    uber_eats_id: str | None = None
    skip_the_dishes_id: str | None = None
    doordash_id: str | None = None
    google_place_id: str | None = None
    business_hours: dict[str, Any] | None = None
    rent_monthly_incl_hst: Decimal | None = None
    contacts: dict[str, Any] | None = None

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, v: str | None) -> str | None:
        if v is not None and (not v.isdigit() or not (4 <= len(v) <= 5)):
            raise ValueError("Store ID must be 4-5 digits")
        return v


class UpdateLocationRequest(BaseModel):
    name: str | None = None
    address: str | None = None
    timezone: str | None = None
    toast_location_id: str | None = None
    store_id: str | None = None
    is_active: bool | None = None
    uber_eats_id: str | None = None
    skip_the_dishes_id: str | None = None
    doordash_id: str | None = None
    google_place_id: str | None = None
    business_hours: dict[str, Any] | None = None
    rent_monthly_incl_hst: Decimal | None = None
    contacts: dict[str, Any] | None = None

    @field_validator("store_id")
    @classmethod
    def validate_store_id(cls, v: str | None) -> str | None:
        if v is not None and (not v.isdigit() or not (4 <= len(v) <= 5)):
            raise ValueError("Store ID must be 4-5 digits")
        return v
