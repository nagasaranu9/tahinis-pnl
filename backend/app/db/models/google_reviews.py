import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleReviewConfig(Base):
    __tablename__ = "google_review_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    place_id: Mapped[str] = mapped_column(String(255), nullable=False)  # Google Place ID
    account_name: Mapped[str | None] = mapped_column(String(500))  # GBP account resource name
    location_name: Mapped[str | None] = mapped_column(String(500))  # GBP location resource name
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "location_id", name="uq_google_review_config_location"),
    )


class GoogleReview(Base):
    __tablename__ = "google_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False)
    review_id: Mapped[str] = mapped_column(String(500), nullable=False)  # Google review resource name
    author_name: Mapped[str | None] = mapped_column(String(255))
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5
    comment: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_comment: Mapped[str | None] = mapped_column(Text)
    reply_update_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "review_id", name="uq_google_review_tenant"),
    )


