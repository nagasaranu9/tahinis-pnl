"""Pipeboard sync service.

Orchestrates OAuth connection, token refresh, data fetch.
Token refresh: checks expiry + 5min buffer, refetches if needed.
Tenant-scoped: all operations filtered by tenant_id.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.security import decrypt_value, encrypt_value
from app.db.models.external_platform import PipeboardAccount
from app.db.repositories.pipeboard_repo import PipeboardRepository
from app.services.external_platforms.pipeboard_adapter import (
    PipeboardAdapter,
    PipeboardAdapterFactory,
)

logger = structlog.get_logger(__name__)


class PipeboardSyncService:
    """Orchestrates Pipeboard OAuth + sync."""

    TOKEN_EXPIRY_BUFFER = 300  # 5 minutes in seconds

    def __init__(
        self,
        db: AsyncSession,
        adapter: Optional[PipeboardAdapter] = None,
    ):
        self._db = db
        self._repo = PipeboardRepository(db)
        self._adapter = adapter or PipeboardAdapterFactory.create("mock")

    async def handle_oauth_callback(
        self,
        tenant_id: uuid.UUID,
        code: str,
        state: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> PipeboardAccount:
        """Exchange OAuth code for tokens and create/update PipeboardAccount."""
        try:
            # Exchange code for tokens
            token_response = await self._adapter.exchange_code_for_token(
                client_id=client_id,
                client_secret=client_secret,
                code=code,
                redirect_uri=redirect_uri,
            )

            access_token = token_response["access_token"]
            refresh_token = token_response.get("refresh_token")
            expires_in = token_response.get("expires_in", 3600)
            token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

            # Encrypt tokens before storage
            access_encrypted = encrypt_value(access_token)
            refresh_encrypted = encrypt_value(refresh_token) if refresh_token else None

            # Fetch user info from Pipeboard (basic call to validate token)
            # For now, use account_id from state or generate one
            pipeboard_account_id = state or f"acc_{uuid.uuid4().hex[:12]}"

            # Create or update account
            account = await self._repo.upsert_pipeboard_account(
                tenant_id=tenant_id,
                pipeboard_account_id=pipeboard_account_id,
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                token_expiry=token_expiry,
                is_active=True,
            )

            logger.info(
                "oauth_callback_success",
                tenant_id=tenant_id,
                pipeboard_account_id=pipeboard_account_id,
            )
            return account

        except Exception as e:
            logger.error(
                "oauth_callback_failed",
                tenant_id=tenant_id,
                error=str(e),
            )
            raise

    async def get_valid_access_token(
        self,
        account: PipeboardAccount,
        client_id: str,
        client_secret: str,
    ) -> Optional[str]:
        """Get valid access token, refreshing if needed.

        Checks if token expires within 5min buffer. If so, refreshes.
        Returns None if refresh fails (account marked inactive).
        """
        if not account.access_token_encrypted:
            logger.warning("no_access_token", account_id=account.id)
            return None

        # Decrypt stored token
        access_token = decrypt_value(account.access_token_encrypted)

        # Check expiry with buffer
        now = datetime.now(UTC)
        expiry_with_buffer = account.token_expiry - timedelta(seconds=self.TOKEN_EXPIRY_BUFFER)

        if account.token_expiry and now > expiry_with_buffer:
            logger.info("token_expired_refreshing", account_id=account.id)
            return await self._refresh_token(
                account=account,
                client_id=client_id,
                client_secret=client_secret,
            )

        return access_token

    async def _refresh_token(
        self,
        account: PipeboardAccount,
        client_id: str,
        client_secret: str,
    ) -> Optional[str]:
        """Refresh token and update account. Returns new access token or None."""
        if not account.refresh_token_encrypted:
            logger.error("no_refresh_token", account_id=account.id)
            await self._mark_account_inactive(account, "no_refresh_token")
            return None

        refresh_token = decrypt_value(account.refresh_token_encrypted)

        try:
            result = await self._adapter.refresh_access_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )

            if not result.success:
                logger.error("token_refresh_failed", account_id=account.id, error=result.error)
                await self._mark_account_inactive(account, result.error)
                return None

            # Update account with new tokens
            access_encrypted = encrypt_value(result.access_token)
            refresh_encrypted = encrypt_value(result.refresh_token)

            await self._repo.update_pipeboard_account_tokens(
                account_id=account.id,
                access_token_encrypted=access_encrypted,
                refresh_token_encrypted=refresh_encrypted,
                token_expiry=result.token_expiry,
            )

            logger.info("token_refresh_success", account_id=account.id)
            return result.access_token

        except Exception as e:
            logger.error("token_refresh_exception", account_id=account.id, error=str(e))
            await self._mark_account_inactive(account, str(e))
            return None

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
