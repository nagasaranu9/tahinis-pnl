from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.email_sync import (
    DriveSyncConfig,
    DriveSyncJob,
    EmailAttachment,
    EmailMessage,
    EmailSyncConfig,
    EmailSyncJob,
)


class EmailSyncRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # EmailSyncConfig
    # ------------------------------------------------------------------

    async def get_config(
        self, tenant_id: uuid.UUID, provider: str, email_address: str
    ) -> Optional[EmailSyncConfig]:
        result = await self._db.execute(
            select(EmailSyncConfig).where(
                EmailSyncConfig.tenant_id == tenant_id,
                EmailSyncConfig.provider == provider,
                EmailSyncConfig.email_address == email_address,
            )
        )
        return result.scalar_one_or_none()

    async def get_config_by_id(
        self, tenant_id: uuid.UUID, config_id: uuid.UUID
    ) -> Optional[EmailSyncConfig]:
        result = await self._db.execute(
            select(EmailSyncConfig).where(
                EmailSyncConfig.tenant_id == tenant_id,
                EmailSyncConfig.id == config_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_configs(
        self, tenant_id: uuid.UUID, provider: Optional[str] = None
    ) -> Sequence[EmailSyncConfig]:
        q = select(EmailSyncConfig).where(
            EmailSyncConfig.tenant_id == tenant_id,
            EmailSyncConfig.is_active.is_(True),
        )
        if provider:
            q = q.where(EmailSyncConfig.provider == provider)
        result = await self._db.execute(q)
        return result.scalars().all()

    async def list_all_active_configs(self) -> Sequence[EmailSyncConfig]:
        result = await self._db.execute(
            select(EmailSyncConfig).where(EmailSyncConfig.is_active.is_(True))
        )
        return result.scalars().all()

    async def upsert_config(
        self,
        tenant_id: uuid.UUID,
        provider: str,
        email_address: str,
        integration_credential_id: uuid.UUID,
    ) -> EmailSyncConfig:
        existing = await self.get_config(tenant_id, provider, email_address)
        if existing:
            existing.integration_credential_id = integration_credential_id
            existing.is_active = True
            await self._db.flush()
            return existing
        config = EmailSyncConfig(
            tenant_id=tenant_id,
            provider=provider,
            email_address=email_address,
            integration_credential_id=integration_credential_id,
        )
        self._db.add(config)
        await self._db.flush()
        return config

    async def update_cursor(
        self,
        config_id: uuid.UUID,
        history_id: Optional[str] = None,
        delta_link: Optional[str] = None,
        last_synced_at: Optional[datetime] = None,
    ) -> None:
        values: dict = {}
        if history_id is not None:
            values["history_id"] = history_id
        if delta_link is not None:
            values["delta_link"] = delta_link
        if last_synced_at is not None:
            values["last_synced_at"] = last_synced_at
        if values:
            await self._db.execute(
                update(EmailSyncConfig).where(EmailSyncConfig.id == config_id).values(**values)
            )

    async def deactivate_config(self, tenant_id: uuid.UUID, config_id: uuid.UUID) -> None:
        await self._db.execute(
            update(EmailSyncConfig)
            .where(EmailSyncConfig.tenant_id == tenant_id, EmailSyncConfig.id == config_id)
            .values(is_active=False)
        )

    # ------------------------------------------------------------------
    # EmailSyncJob
    # ------------------------------------------------------------------

    async def create_job(
        self,
        tenant_id: uuid.UUID,
        config_id: uuid.UUID,
        provider: str,
        triggered_by: Optional[uuid.UUID] = None,
    ) -> EmailSyncJob:
        job = EmailSyncJob(
            tenant_id=tenant_id,
            config_id=config_id,
            provider=provider,
            triggered_by=triggered_by,
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def update_job(
        self,
        job_id: uuid.UUID,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        messages_scanned: int = 0,
        attachments_found: int = 0,
        documents_created: int = 0,
        duplicates_skipped: int = 0,
    ) -> None:
        values: dict = {"status": status}
        if started_at:
            values["started_at"] = started_at
        if completed_at:
            values["completed_at"] = completed_at
        if error_message is not None:
            values["error_message"] = error_message
        if messages_scanned:
            values["messages_scanned"] = messages_scanned
        if attachments_found:
            values["attachments_found"] = attachments_found
        if documents_created:
            values["documents_created"] = documents_created
        if duplicates_skipped:
            values["duplicates_skipped"] = duplicates_skipped
        await self._db.execute(
            update(EmailSyncJob).where(EmailSyncJob.id == job_id).values(**values)
        )

    async def list_jobs(
        self,
        tenant_id: uuid.UUID,
        config_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[EmailSyncJob], int]:
        q = select(EmailSyncJob).where(EmailSyncJob.tenant_id == tenant_id)
        if config_id:
            q = q.where(EmailSyncJob.config_id == config_id)
        q = q.order_by(EmailSyncJob.created_at.desc()).limit(limit).offset(offset)
        rows = (await self._db.execute(q)).scalars().all()

        from sqlalchemy import func
        count_q = select(func.count()).select_from(EmailSyncJob).where(
            EmailSyncJob.tenant_id == tenant_id
        )
        if config_id:
            count_q = count_q.where(EmailSyncJob.config_id == config_id)
        total = (await self._db.execute(count_q)).scalar_one()
        return rows, total

    # ------------------------------------------------------------------
    # EmailMessage dedup
    # ------------------------------------------------------------------

    async def message_exists(
        self, tenant_id: uuid.UUID, provider: str, provider_message_id: str
    ) -> bool:
        result = await self._db.execute(
            select(EmailMessage.id).where(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.provider == provider,
                EmailMessage.provider_message_id == provider_message_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def upsert_message(self, row: dict) -> uuid.UUID:
        stmt = (
            pg_insert(EmailMessage)
            .values(**row)
            .on_conflict_do_nothing(constraint="uq_email_message")
            .returning(EmailMessage.id)
        )
        result = await self._db.execute(stmt)
        returned = result.fetchone()
        if returned:
            return returned[0]
        existing = await self._db.execute(
            select(EmailMessage.id).where(
                EmailMessage.tenant_id == row["tenant_id"],
                EmailMessage.provider == row["provider"],
                EmailMessage.provider_message_id == row["provider_message_id"],
            )
        )
        return existing.scalar_one()

    async def save_attachment(self, row: dict) -> EmailAttachment:
        att = EmailAttachment(**row)
        self._db.add(att)
        await self._db.flush()
        return att

    async def mark_message_processed(self, message_id: uuid.UUID) -> None:
        await self._db.execute(
            update(EmailMessage).where(EmailMessage.id == message_id).values(processed=True)
        )

    # ------------------------------------------------------------------
    # DriveSyncConfig
    # ------------------------------------------------------------------

    async def get_drive_config(
        self, tenant_id: uuid.UUID, email_address: str
    ) -> Optional[DriveSyncConfig]:
        result = await self._db.execute(
            select(DriveSyncConfig).where(
                DriveSyncConfig.tenant_id == tenant_id,
                DriveSyncConfig.email_address == email_address,
            )
        )
        return result.scalar_one_or_none()

    async def list_drive_configs(self, tenant_id: uuid.UUID) -> Sequence[DriveSyncConfig]:
        result = await self._db.execute(
            select(DriveSyncConfig).where(
                DriveSyncConfig.tenant_id == tenant_id,
                DriveSyncConfig.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def list_all_active_drive_configs(self) -> Sequence[DriveSyncConfig]:
        result = await self._db.execute(
            select(DriveSyncConfig).where(DriveSyncConfig.is_active.is_(True))
        )
        return result.scalars().all()

    async def upsert_drive_config(
        self,
        tenant_id: uuid.UUID,
        email_address: str,
        integration_credential_id: uuid.UUID,
    ) -> DriveSyncConfig:
        existing = await self.get_drive_config(tenant_id, email_address)
        if existing:
            existing.integration_credential_id = integration_credential_id
            existing.is_active = True
            await self._db.flush()
            return existing
        config = DriveSyncConfig(
            tenant_id=tenant_id,
            email_address=email_address,
            integration_credential_id=integration_credential_id,
        )
        self._db.add(config)
        await self._db.flush()
        return config

    async def update_drive_cursor(
        self,
        config_id: uuid.UUID,
        page_token: Optional[str],
        last_synced_at: datetime,
    ) -> None:
        await self._db.execute(
            update(DriveSyncConfig)
            .where(DriveSyncConfig.id == config_id)
            .values(page_token=page_token, last_synced_at=last_synced_at)
        )

    async def create_drive_job(
        self,
        tenant_id: uuid.UUID,
        config_id: uuid.UUID,
        triggered_by: Optional[uuid.UUID] = None,
    ) -> DriveSyncJob:
        job = DriveSyncJob(
            tenant_id=tenant_id,
            config_id=config_id,
            triggered_by=triggered_by,
        )
        self._db.add(job)
        await self._db.flush()
        return job

    async def update_drive_job(
        self,
        job_id: uuid.UUID,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        files_scanned: int = 0,
        documents_created: int = 0,
        duplicates_skipped: int = 0,
    ) -> None:
        values: dict = {"status": status}
        if started_at:
            values["started_at"] = started_at
        if completed_at:
            values["completed_at"] = completed_at
        if error_message is not None:
            values["error_message"] = error_message
        if files_scanned:
            values["files_scanned"] = files_scanned
        if documents_created:
            values["documents_created"] = documents_created
        if duplicates_skipped:
            values["duplicates_skipped"] = duplicates_skipped
        await self._db.execute(
            update(DriveSyncJob).where(DriveSyncJob.id == job_id).values(**values)
        )

    async def list_drive_jobs(
        self,
        tenant_id: uuid.UUID,
        config_id: Optional[uuid.UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Sequence[DriveSyncJob], int]:
        q = select(DriveSyncJob).where(DriveSyncJob.tenant_id == tenant_id)
        if config_id:
            q = q.where(DriveSyncJob.config_id == config_id)
        q = q.order_by(DriveSyncJob.created_at.desc()).limit(limit).offset(offset)
        rows = (await self._db.execute(q)).scalars().all()

        from sqlalchemy import func
        count_q = select(func.count()).select_from(DriveSyncJob).where(
            DriveSyncJob.tenant_id == tenant_id
        )
        if config_id:
            count_q = count_q.where(DriveSyncJob.config_id == config_id)
        total = (await self._db.execute(count_q)).scalar_one()
        return rows, total
