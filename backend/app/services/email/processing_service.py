"""
EmailProcessingService — orchestrates email/drive sync → document pipeline.

Flow:
1. Fetch new messages/files from provider
2. Dedup by provider_message_id (email) or SHA-256 (attachments/files)
3. For each supported attachment/file: call ingest_document (existing P1 pipeline)
4. Save EmailMessage + EmailAttachment records
5. Update cursor (historyId / deltaLink / pageToken)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value
from app.db.models.email_sync import DriveSyncConfig, EmailSyncConfig
from app.db.models.integration import IntegrationCredential
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.email_repo import EmailSyncRepository
from app.services.document_service import ingest_document

logger = structlog.get_logger(__name__)

_NIL_UUID = uuid.UUID(int=0)


class EmailSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = EmailSyncRepository(db)

    async def sync_gmail(
        self,
        tenant_id: uuid.UUID,
        config: EmailSyncConfig,
        job_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        from app.services.email.gmail_client import (
            GmailClient,
            extract_attachments,
            extract_message_metadata,
        )

        creds = await self._load_creds(config.integration_credential_id)
        log = logger.bind(tenant_id=str(tenant_id), provider="gmail", job_id=str(job_id))

        messages_scanned = attachments_found = documents_created = duplicates_skipped = 0

        async with GmailClient(creds["access_token"], creds["refresh_token"]) as client:
            raw_messages, new_history_id, new_access_token = (
                await client.list_messages_with_attachments(history_id=config.history_id)
            )
            log.info("gmail_messages_fetched", count=len(raw_messages))

            for raw_msg in raw_messages:
                msg_id = raw_msg.get("id", "")
                if not msg_id:
                    continue

                already = await self._repo.message_exists(tenant_id, "gmail", msg_id)
                if already:
                    duplicates_skipped += 1
                    continue

                try:
                    full_msg, _ = await client.get_message(msg_id)
                except ValueError as exc:
                    # Message appeared in history.list but is gone (deleted/moved/
                    # purged). 404 here must not kill the whole sync — skip it.
                    if "404" in str(exc):
                        log.warning("gmail_message_gone", msg_id=msg_id)
                        continue
                    raise
                meta = extract_message_metadata(full_msg)
                attachments_in_msg = extract_attachments(full_msg)

                db_msg_id = await self._repo.upsert_message({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "config_id": config.id,
                    "provider": "gmail",
                    "provider_message_id": msg_id,
                    "subject": meta["subject"],
                    "sender": meta["sender"],
                    "received_at": meta["received_at"],
                    "has_attachments": bool(attachments_in_msg),
                })
                messages_scanned += 1

                for att in attachments_in_msg:
                    if att["mime_type"].startswith("image/"):
                        continue
                    attachments_found += 1
                    try:
                        content = await client.get_attachment(msg_id, att["attachment_id"])
                        doc, _ = await ingest_document(
                            file_bytes=content,
                            original_filename=att["filename"],
                            mime_type=att["mime_type"],
                            tenant_id=tenant_id,
                            created_by=user_id or await self._get_system_user_id(tenant_id),
                            repo=DocumentRepository(self._db),
                            source="email_gmail",
                        )
                        await self._repo.save_attachment({
                            "id": uuid.uuid4(),
                            "tenant_id": tenant_id,
                            "message_id": db_msg_id,
                            "document_id": doc.id if doc else None,
                            "filename": att["filename"],
                            "mime_type": att["mime_type"],
                            "file_size_bytes": att.get("size"),
                            "provider_attachment_id": att["attachment_id"],
                        })
                        if doc:
                            documents_created += 1
                        else:
                            duplicates_skipped += 1
                    except Exception as e:
                        log.warning("gmail_attachment_failed", filename=att["filename"], error=str(e))

                await self._repo.mark_message_processed(db_msg_id)

        # Update cursor
        await self._repo.update_cursor(
            config_id=config.id,
            history_id=new_history_id,
            last_synced_at=datetime.now(UTC),
        )
        # Update stored access token if refreshed
        if new_access_token != creds["access_token"]:
            await self._update_access_token(config.integration_credential_id, new_access_token)

        await self._db.commit()

        return {
            "messages_scanned": messages_scanned,
            "attachments_found": attachments_found,
            "documents_created": documents_created,
            "duplicates_skipped": duplicates_skipped,
        }

    async def sync_gmail_historical(
        self,
        tenant_id: uuid.UUID,
        config: EmailSyncConfig,
        job_id: uuid.UUID,
        after_date: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        """Historical Gmail import from a specific date. Resets history_id cursor after."""
        from app.services.email.gmail_client import (
            GmailClient,
            extract_attachments,
            extract_message_metadata,
        )

        creds = await self._load_creds(config.integration_credential_id)
        log = logger.bind(tenant_id=str(tenant_id), provider="gmail_historical", job_id=str(job_id))
        log.info("gmail_historical_start", after_date=after_date)

        messages_scanned = attachments_found = documents_created = duplicates_skipped = 0

        # after_date must be YYYY/MM/DD for Gmail API
        gmail_date = after_date.replace("-", "/")

        async with GmailClient(creds["access_token"], creds["refresh_token"]) as client:
            # Full scan with date filter; no history_id so it does _full_scan_messages
            raw_messages, new_history_id, new_access_token = (
                await client.list_messages_with_attachments(
                    history_id=None,
                    max_results=2000,
                    after_date=gmail_date,
                )
            )
            log.info("gmail_historical_messages_fetched", count=len(raw_messages))

            for raw_msg in raw_messages:
                msg_id = raw_msg.get("id", "")
                if not msg_id:
                    continue

                already = await self._repo.message_exists(tenant_id, "gmail", msg_id)
                if already:
                    duplicates_skipped += 1
                    continue

                try:
                    full_msg, _ = await client.get_message(msg_id)
                except ValueError as exc:
                    # Message appeared in history.list but is gone (deleted/moved/
                    # purged). 404 here must not kill the whole sync — skip it.
                    if "404" in str(exc):
                        log.warning("gmail_message_gone", msg_id=msg_id)
                        continue
                    raise
                meta = extract_message_metadata(full_msg)
                attachments_in_msg = extract_attachments(full_msg)

                db_msg_id = await self._repo.upsert_message({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "config_id": config.id,
                    "provider": "gmail",
                    "provider_message_id": msg_id,
                    "subject": meta["subject"],
                    "sender": meta["sender"],
                    "received_at": meta["received_at"],
                    "has_attachments": bool(attachments_in_msg),
                })
                messages_scanned += 1

                for att in attachments_in_msg:
                    if att["mime_type"].startswith("image/"):
                        continue
                    attachments_found += 1
                    try:
                        from app.db.repositories.document_repo import DocumentRepository
                        content = await client.get_attachment(msg_id, att["attachment_id"])
                        doc, _ = await ingest_document(
                            file_bytes=content,
                            original_filename=att["filename"],
                            mime_type=att["mime_type"],
                            tenant_id=tenant_id,
                            created_by=user_id or await self._get_system_user_id(tenant_id),
                            repo=DocumentRepository(self._db),
                            source="email_gmail",
                        )
                        await self._repo.save_attachment({
                            "id": uuid.uuid4(),
                            "tenant_id": tenant_id,
                            "message_id": db_msg_id,
                            "document_id": doc.id if doc else None,
                            "filename": att["filename"],
                            "mime_type": att["mime_type"],
                            "file_size_bytes": att.get("size"),
                            "provider_attachment_id": att["attachment_id"],
                        })
                        if doc:
                            documents_created += 1
                        else:
                            duplicates_skipped += 1
                    except Exception as e:
                        log.warning("gmail_historical_attachment_failed", filename=att["filename"], error=str(e))

                await self._repo.mark_message_processed(db_msg_id)

        # Update cursor to latest history_id so next daily sync is incremental
        await self._repo.update_cursor(
            config_id=config.id,
            history_id=new_history_id,
            last_synced_at=datetime.now(UTC),
        )
        if new_access_token != creds["access_token"]:
            await self._update_access_token(config.integration_credential_id, new_access_token)

        await self._db.commit()
        log.info("gmail_historical_complete", messages_scanned=messages_scanned,
                 documents_created=documents_created)

        return {
            "messages_scanned": messages_scanned,
            "attachments_found": attachments_found,
            "documents_created": documents_created,
            "duplicates_skipped": duplicates_skipped,
        }

    async def sync_outlook(
        self,
        tenant_id: uuid.UUID,
        config: EmailSyncConfig,
        job_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        from app.services.email.outlook_client import (
            OutlookClient,
            extract_outlook_metadata,
            SUPPORTED_ATTACHMENT_MIMES,
        )

        creds = await self._load_creds(config.integration_credential_id)
        log = logger.bind(tenant_id=str(tenant_id), provider="outlook", job_id=str(job_id))

        messages_scanned = attachments_found = documents_created = duplicates_skipped = 0

        async with OutlookClient(creds["access_token"], creds["refresh_token"]) as client:
            raw_messages, new_delta_link, new_token = await client.list_messages_delta(
                delta_link=config.delta_link
            )
            log.info("outlook_messages_fetched", count=len(raw_messages))

            for raw_msg in raw_messages:
                msg_id = raw_msg.get("id", "")
                if not msg_id or not raw_msg.get("hasAttachments"):
                    continue

                already = await self._repo.message_exists(tenant_id, "outlook", msg_id)
                if already:
                    duplicates_skipped += 1
                    continue

                meta = extract_outlook_metadata(raw_msg)
                db_msg_id = await self._repo.upsert_message({
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_id,
                    "config_id": config.id,
                    "provider": "outlook",
                    "provider_message_id": msg_id,
                    "subject": meta["subject"],
                    "sender": meta["sender"],
                    "received_at": meta["received_at"],
                    "has_attachments": True,
                })
                messages_scanned += 1

                attachments, _ = await client.get_message_attachments(msg_id)
                for att in attachments:
                    ct = att.get("contentType", "")
                    if ct not in SUPPORTED_ATTACHMENT_MIMES:
                        continue
                    attachments_found += 1
                    try:
                        content = await client.download_attachment(msg_id, att["id"])
                        doc, _ = await ingest_document(
                            file_bytes=content,
                            original_filename=att.get("name", "attachment"),
                            mime_type=ct,
                            tenant_id=tenant_id,
                            created_by=user_id or await self._get_system_user_id(tenant_id),
                            repo=DocumentRepository(self._db),
                            source="email_outlook",
                        )
                        await self._repo.save_attachment({
                            "id": uuid.uuid4(),
                            "tenant_id": tenant_id,
                            "message_id": db_msg_id,
                            "document_id": doc.id if doc else None,
                            "filename": att.get("name", "attachment"),
                            "mime_type": ct,
                            "file_size_bytes": att.get("size"),
                            "provider_attachment_id": att["id"],
                        })
                        if doc:
                            documents_created += 1
                        else:
                            duplicates_skipped += 1
                    except Exception as e:
                        log.warning("outlook_attachment_failed", filename=att.get("name"), error=str(e))

                await self._repo.mark_message_processed(db_msg_id)

        if new_delta_link:
            await self._repo.update_cursor(
                config_id=config.id,
                delta_link=new_delta_link,
                last_synced_at=datetime.now(UTC),
            )
        if new_token != creds["access_token"]:
            await self._update_access_token(config.integration_credential_id, new_token)

        await self._db.commit()

        return {
            "messages_scanned": messages_scanned,
            "attachments_found": attachments_found,
            "documents_created": documents_created,
            "duplicates_skipped": duplicates_skipped,
        }

    async def sync_drive(
        self,
        tenant_id: uuid.UUID,
        config: DriveSyncConfig,
        job_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> dict:
        from app.services.email.drive_client import GoogleDriveClient
        import json

        creds = await self._load_creds(config.integration_credential_id)
        log = logger.bind(tenant_id=str(tenant_id), provider="gdrive", job_id=str(job_id))

        folder_ids = json.loads(config.folder_ids) if config.folder_ids else None
        files_scanned = documents_created = duplicates_skipped = 0
        page_token = config.page_token

        async with GoogleDriveClient(creds["access_token"], creds["refresh_token"]) as client:
            while True:
                files, next_token, new_token = await client.list_files(
                    page_token=page_token,
                    folder_ids=folder_ids,
                )
                log.info("drive_files_batch", count=len(files), has_next=bool(next_token))

                for f in files:
                    files_scanned += 1
                    try:
                        content = await client.download_file(f["id"])
                        doc, _ = await ingest_document(
                            file_bytes=content,
                            original_filename=f.get("name", "file"),
                            mime_type=f.get("mimeType", "application/octet-stream"),
                            tenant_id=tenant_id,
                            created_by=user_id or await self._get_system_user_id(tenant_id),
                            repo=DocumentRepository(self._db),
                            source="google_drive",
                        )
                        if doc:
                            documents_created += 1
                        else:
                            duplicates_skipped += 1
                    except Exception as e:
                        log.warning("drive_file_failed", file_id=f["id"], error=str(e))

                page_token = next_token
                if not next_token:
                    break

            if new_token != creds["access_token"]:
                await self._update_access_token(config.integration_credential_id, new_token)

        await self._repo.update_drive_cursor(
            config_id=config.id,
            page_token=page_token,
            last_synced_at=datetime.now(UTC),
        )
        await self._db.commit()

        return {
            "files_scanned": files_scanned,
            "documents_created": documents_created,
            "duplicates_skipped": duplicates_skipped,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_system_user_id(self, tenant_id: uuid.UUID) -> uuid.UUID:
        """Return tenant owner user_id for system-initiated document ingestion."""
        from sqlalchemy import select
        from app.db.models.user import User
        result = await self._db.execute(
            select(User.id).where(User.tenant_id == tenant_id, User.role == "owner").limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            result = await self._db.execute(
                select(User.id).where(User.tenant_id == tenant_id).limit(1)
            )
            row = result.scalar_one_or_none()
        if row is None:
            raise ValueError(f"No user found for tenant {tenant_id}")
        return row

    async def _load_creds(self, credential_id: Optional[uuid.UUID]) -> dict:
        if not credential_id:
            raise ValueError("No integration credential")
        from sqlalchemy import select
        result = await self._db.execute(
            select(IntegrationCredential).where(IntegrationCredential.id == credential_id)
        )
        cred = result.scalar_one_or_none()
        if not cred:
            raise ValueError(f"IntegrationCredential {credential_id} not found")
        return {
            "access_token": decrypt_value(cred.access_token_encrypted),
            "refresh_token": decrypt_value(cred.refresh_token_encrypted),
        }

    async def _update_access_token(
        self, credential_id: uuid.UUID, new_access_token: str
    ) -> None:
        from app.core.security import encrypt_value
        from sqlalchemy import update
        await self._db.execute(
            update(IntegrationCredential)
            .where(IntegrationCredential.id == credential_id)
            .values(access_token_encrypted=encrypt_value(new_access_token))
        )
