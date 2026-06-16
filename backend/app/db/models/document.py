import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantMixin, TimestampMixin

DOCUMENT_STATUSES = {
    "pending",
    "ocr_processing",
    "ocr_complete",
    "extracting",
    "extracted",
    "categorized",
    "reconciled",
    "error",
}

DOCUMENT_TYPES = {"invoice", "receipt", "bill", "statement", "other"}

DOCUMENT_SOURCES = {"email_gmail", "email_outlook", "gdrive", "manual_upload"}

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}


class Document(Base, TenantMixin, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual_upload")
    source_id: Mapped[str | None] = mapped_column(String(512))  # external dedup key
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # immutable object key
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    document_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    ocr_results: Mapped[list["OCRResult"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    line_items: Mapped[list["ExtractedLineItem"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class OCRResult(Base, TenantMixin):
    __tablename__ = "ocr_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="mock")
    raw_response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )

    document: Mapped["Document"] = relationship(back_populates="ocr_results")


class ExtractedLineItem(Base, TenantMixin, TimestampMixin):
    __tablename__ = "extracted_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ocr_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ocr_results.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="CAD")
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    manually_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    corrected_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document: Mapped["Document"] = relationship(back_populates="line_items")
