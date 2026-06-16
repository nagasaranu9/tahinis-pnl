from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, TenantMixin


class EmailSyncConfig(Base, TimestampMixin, TenantMixin):
    """Per-tenant, per-provider email OAuth config and sync cursor."""

    __tablename__ = "email_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # gmail | outlook
    integration_credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True
    )
    email_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Incremental sync cursors
    history_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)   # Gmail: historyId
    delta_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)           # Outlook: deltaLink
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "email_address", name="uq_email_sync_config"),
    )


class EmailSyncJob(Base, TimestampMixin, TenantMixin):
    __tablename__ = "email_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_sync_configs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    messages_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attachments_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


class EmailMessage(Base, TimestampMixin, TenantMixin):
    """Deduplicated record of a processed email message."""

    __tablename__ = "email_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_sync_configs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    attachments: Mapped[list[EmailAttachment]] = relationship(
        "EmailAttachment", back_populates="message", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "provider_message_id", name="uq_email_message"),
    )


class EmailAttachment(Base, TimestampMixin, TenantMixin):
    """Links an email attachment to its processed document record."""

    __tablename__ = "email_attachments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_messages.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    provider_attachment_id: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    message: Mapped[EmailMessage] = relationship("EmailMessage", back_populates="attachments")


class DriveSyncConfig(Base, TimestampMixin, TenantMixin):
    """Google Drive OAuth config and incremental sync cursor."""

    __tablename__ = "drive_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    integration_credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("integration_credentials.id", ondelete="SET NULL"), nullable=True
    )
    email_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    page_token: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    folder_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array of folder IDs to watch
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "email_address", name="uq_drive_sync_config"),
    )


class DriveSyncJob(Base, TimestampMixin, TenantMixin):
    __tablename__ = "drive_sync_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drive_sync_configs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    files_scanned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    documents_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
