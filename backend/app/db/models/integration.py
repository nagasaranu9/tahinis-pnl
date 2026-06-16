import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantMixin, TimestampMixin

PROVIDERS = {
    "toast",
    "gmail",
    "outlook",
    "gdrive",
    "google_ads",
    "google_business",
    "meta_ads",
    "pushoperations",
}


class IntegrationCredential(Base, TenantMixin, TimestampMixin):
    __tablename__ = "integration_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # Tokens stored AES-256-GCM encrypted. Never log these fields.
    access_token_encrypted: Mapped[str | None] = mapped_column(String(2048))
    refresh_token_encrypted: Mapped[str | None] = mapped_column(String(2048))
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra_config: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
