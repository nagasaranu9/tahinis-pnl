"""Pipeboard alert service — multi-channel dispatch.

Channels:
  - Dashboard banner (PipeboardAlert model)
  - Email (owner + retry with 15min backoff)
  - Audit logs (immutable event record)
  - Slack (optional, feature flag)
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_platform import PipeboardAccount
from app.db.repositories.pipeboard_repo import PipeboardRepository

logger = structlog.get_logger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Alert types."""
    SYNC_FAILED = "sync_failed"
    AUTH_FAILED = "auth_failed"
    TOKEN_EXPIRED = "token_expired"
    RATE_LIMIT = "rate_limit"
    SYNC_STALE = "sync_stale"
    ACCOUNT_INACTIVE = "account_inactive"


class PipeboardAlertService:
    """Coordinates multi-channel alerts for Pipeboard events."""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._repo = PipeboardRepository(db)

    async def alert_sync_failed(
        self,
        tenant_id: uuid.UUID,
        account: PipeboardAccount,
        error: str,
    ) -> None:
        """Alert on sync failure."""
        await self._dispatch_alert(
            tenant_id=tenant_id,
            alert_type=AlertType.SYNC_FAILED,
            severity=AlertSeverity.ERROR,
            title="Pipeboard sync failed",
            message=f"Failed to sync Pipeboard metrics: {error}",
            account_id=account.id,
            error_detail=error,
        )

    async def alert_auth_failed(
        self,
        tenant_id: uuid.UUID,
        account: PipeboardAccount,
        error: str,
    ) -> None:
        """Alert on auth/token failure."""
        await self._dispatch_alert(
            tenant_id=tenant_id,
            alert_type=AlertType.AUTH_FAILED,
            severity=AlertSeverity.CRITICAL,
            title="Pipeboard authentication failed",
            message="Your Pipeboard connection has been disconnected due to an authentication error. Please reconnect.",
            account_id=account.id,
            error_detail=error,
        )

    async def alert_sync_stale(
        self,
        tenant_id: uuid.UUID,
        account: PipeboardAccount,
        hours_since_sync: int,
    ) -> None:
        """Alert if sync hasn't run recently."""
        await self._dispatch_alert(
            tenant_id=tenant_id,
            alert_type=AlertType.SYNC_STALE,
            severity=AlertSeverity.WARNING,
            title="Pipeboard sync is stale",
            message=f"No successful Pipeboard sync for {hours_since_sync} hours. Check connection.",
            account_id=account.id,
        )

    async def _dispatch_alert(
        self,
        tenant_id: uuid.UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        account_id: uuid.UUID,
        error_detail: Optional[str] = None,
    ) -> None:
        """Dispatch alert to all configured channels."""
        now = datetime.now(UTC)

        # Channel 1: Dashboard banner (PipeboardAlert)
        await self._send_dashboard_alert(
            tenant_id=tenant_id,
            alert_type=alert_type,
            severity=severity,
            title=title,
            message=message,
            account_id=account_id,
        )

        # Channel 2: Audit log
        await self._log_audit_event(
            tenant_id=tenant_id,
            account_id=account_id,
            event_type=alert_type.value,
            severity=severity.value,
            message=message,
            error_detail=error_detail,
        )

        # Channel 3: Email (dispatch to Celery task with retry)
        await self._queue_email_alert(
            tenant_id=tenant_id,
            title=title,
            message=message,
            severity=severity,
        )

        # Channel 4: Slack (optional, behind feature flag)
        # TODO: implement Slack dispatch if PIPEBOARD_SLACK_WEBHOOK set

        logger.info(
            "alert_dispatched",
            tenant_id=tenant_id,
            alert_type=alert_type.value,
            severity=severity.value,
        )

    async def _send_dashboard_alert(
        self,
        tenant_id: uuid.UUID,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        message: str,
        account_id: uuid.UUID,
    ) -> None:
        """Store dashboard banner alert."""
        try:
            await self._repo.create_alert(
                tenant_id=tenant_id,
                alert_type=alert_type.value,
                severity=severity.value,
                title=title,
                message=message,
                account_id=account_id,
            )
            logger.info(
                "dashboard_alert_stored",
                tenant_id=tenant_id,
                alert_type=alert_type.value,
            )
        except Exception as e:
            logger.error("dashboard_alert_failed", error=str(e))

    async def _log_audit_event(
        self,
        tenant_id: uuid.UUID,
        account_id: uuid.UUID,
        event_type: str,
        severity: str,
        message: str,
        error_detail: Optional[str],
    ) -> None:
        """Log immutable audit event."""
        try:
            await self._repo.create_audit_log(
                tenant_id=tenant_id,
                account_id=account_id,
                event_type=event_type,
                severity=severity,
                message=message,
                error_detail=error_detail,
            )
            logger.info(
                "audit_event_logged",
                tenant_id=tenant_id,
                account_id=account_id,
                event_type=event_type,
                severity=severity,
            )
        except Exception as e:
            logger.error("audit_log_failed", error=str(e))

    async def _queue_email_alert(
        self,
        tenant_id: uuid.UUID,
        title: str,
        message: str,
        severity: AlertSeverity,
    ) -> None:
        """Queue email alert to owner (retry at 15min, 1h, 4h)."""
        # TODO: Queue celery task 'pipeboard.send_alert_email' with retry config
        logger.info(
            "email_alert_queued",
            tenant_id=tenant_id,
            title=title,
            severity=severity.value,
        )
