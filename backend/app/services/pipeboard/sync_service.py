"""Pipeboard sync service.

Auth = a single Pipeboard API token per tenant (no OAuth / refresh flow).
The token is stored encrypted in PipeboardAccount.access_token_encrypted and
is long-lived. Tenant-scoped: all operations filtered by tenant_id.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.db.models.external_platform import PipeboardAccount
from app.db.repositories.pipeboard_repo import PipeboardRepository
from app.services.external_platforms.pipeboard_adapter import (
    PipeboardAdapter,
    PipeboardAdapterFactory,
)

logger = structlog.get_logger(__name__)

# API tokens are long-lived; store a far-future "expiry" sentinel for schema reuse.
_TOKEN_TTL = timedelta(days=3650)


class PipeboardSyncService:
    """Orchestrates Pipeboard token connection + sync."""

    def __init__(
        self,
        db: AsyncSession,
        adapter: Optional[PipeboardAdapter] = None,
    ):
        from app.core.config import settings
        self._db = db
        self._repo = PipeboardRepository(db)
        self._adapter = adapter or PipeboardAdapterFactory.create(settings.PIPEBOARD_ADAPTER)

    async def connect_with_token(
        self,
        tenant_id: uuid.UUID,
        api_token: str,
        platform: str = "google_ads",
    ) -> PipeboardAccount:
        """Validate a Pipeboard API token, then create/update the account.

        Validation = list accounts on the platform's MCP server. Raises on
        failure so the caller can return 400 (bad token / no access).
        """
        accounts = await self._adapter.list_accounts(api_token, platform)
        if not accounts:
            raise ValueError("no_ad_accounts_accessible")

        # Use the first ad-account id as the stable pipeboard_account_id.
        pipeboard_account_id = str(accounts[0].get("id") or f"acc_{uuid.uuid4().hex[:12]}")
        token_expiry = datetime.now(UTC) + _TOKEN_TTL

        account = await self._repo.upsert_pipeboard_account(
            tenant_id=tenant_id,
            pipeboard_account_id=pipeboard_account_id,
            access_token_encrypted=encrypt_value(api_token),
            refresh_token_encrypted=None,
            token_expiry=token_expiry,
            is_active=True,
        )
        logger.info("pipeboard_connected", tenant_id=tenant_id, account_id=pipeboard_account_id)
        return account

    def get_api_token(self, account: PipeboardAccount) -> Optional[str]:
        """Decrypt and return the stored Pipeboard API token."""
        if not account.access_token_encrypted:
            logger.warning("no_api_token", account_id=account.id)
            return None
        return decrypt_value(account.access_token_encrypted)

    async def _mark_account_inactive(
        self,
        account: PipeboardAccount,
        error: Optional[str] = None,
    ) -> None:
        """Mark account inactive due to auth failure."""
        await self._repo.update_pipeboard_account(
            account_id=account.id,
            is_active=False,
            last_sync_error=error or "authentication_failed",
        )

    async def disconnect_account(
        self,
        tenant_id: uuid.UUID,
        account_id: uuid.UUID,
    ) -> None:
        """Revoke access and delete account."""
        account = await self._repo.get_pipeboard_account(account_id)
        if not account or account.tenant_id != tenant_id:
            raise ValueError("account_not_found_or_unauthorized")

        # Delete associated data
        await self._repo.delete_pipeboard_account(account_id)
        logger.info("account_disconnected", account_id=account_id, tenant_id=tenant_id)

    async def get_account_status(
        self,
        tenant_id: uuid.UUID,
    ) -> dict:
        """Get connection status for tenant."""
        account = await self._repo.get_active_pipeboard_account(tenant_id)
        if not account:
            return {
                "connected": False,
                "account_id": None,
                "is_active": False,
                "last_sync_at": None,
                "last_sync_error": None,
            }

        return {
            "connected": True,
            "account_id": str(account.id),
            "is_active": account.is_active,
            "last_sync_at": account.last_sync_at.isoformat() if account.last_sync_at else None,
            "last_sync_error": account.last_sync_error,
            "pipeboard_account_id": account.pipeboard_account_id,
        }
