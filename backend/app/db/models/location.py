import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin


class Location(Base, TenantMixin, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    toast_location_id: Mapped[str | None] = mapped_column(String(255), unique=False)
    store_id: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Onboarding invite — set when an owner is invited to fill out Settings for this location
    invite_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invite_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    invite_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")

    # Delivery platform IDs
    uber_eats_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    skip_the_dishes_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doordash_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Google integration
    google_place_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    business_hours: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Financial
    rent_monthly_incl_hst: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Contacts: {owner_1, owner_2, manager_1, manager_2} each {name, email, phone}
    contacts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="locations")  # type: ignore[name-defined]
