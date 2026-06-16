import uuid

from pydantic import BaseModel, field_validator


class TenantResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    timezone: str
    currency_code: str
    plan: str
    is_active: bool

    model_config = {"from_attributes": True}


class UpdateTenantRequest(BaseModel):
    name: str | None = None
    timezone: str | None = None
    currency_code: str | None = None

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, v: str | None) -> str | None:
        if v is not None and len(v) != 3:
            raise ValueError("currency_code must be 3 characters (ISO 4217)")
        return v.upper() if v else v
