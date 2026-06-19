"""Pipeboard sync Celery tasks.

sync_pipeboard_incremental  — sync since last sync
sync_pipeboard_historical   — backfill date range (chunked)
daily_pipeboard_sync_all_tenants — Beat entry (incremental)
"""
import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Optional

import structlog

from app.core.config import settings
from app.db.session import get_db_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Rate limiting: Pipeboard API defaults (adjust per docs)
PIPEBOARD_RATE_LIMIT_REQUESTS = 300  # requests per minute
PIPEBOARD_RATE_LIMIT_WINDOW = 60  # seconds

CHUNK_DAYS = 30  # historical backfill chunk size


@celery_app.task(
    name="pipeboard.sync_incremental",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="sync",
)
def sync_pipeboard_incremental(
    self,
    tenant_id: str,
) -> dict:
    """Sync latest metrics since last sync."""
    return asyncio.run(_sync_incremental(self, tenant_id))


@celery_app.task(
    name="pipeboard.sync_historical",
    bind=True,
    max_retries=3,
    default_retry_delay=900,
    queue="sync",
)
def sync_pipeboard_historical(
    self,
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    pipeboard_platform: Optional[str] = None,
) -> dict:
    """Backfill historical metrics (chunked by CHUNK_DAYS)."""
    return asyncio.run(
        _sync_historical(
            self,
            tenant_id,
            date_from,
            date_to,
            pipeboard_platform,
        )
    )


async def _sync_incremental(self, tenant_id: str) -> dict:
    """Sync latest metrics since last sync for tenant."""
    from app.db.repositories.pipeboard_repo import PipeboardRepository
    from app.services.pipeboard.sync_service import PipeboardSyncService
    from app.services.pipeboard.backfill_service import PipeboardBackfillService

    async with get_db_context() as db:
        repo = PipeboardRepository(db)
        sync_service = PipeboardSyncService(db)
        backfill_service = PipeboardBackfillService(db)

        tenant_uuid = uuid.UUID(tenant_id)

        # Check account active
        account = await repo.get_active_pipeboard_account(tenant_uuid)
        if not account:
            logger.warning("no_active_account", tenant_id=tenant_id)
            return {"success": False, "error": "no_active_account"}

        try:
            # Get valid access token (refreshes if needed)
            access_token = await sync_service.get_valid_access_token(
                account,
                client_id=settings.PIPEBOARD_CLIENT_ID,
                client_secret=settings.PIPEBOARD_CLIENT_SECRET,
            )
            if not access_token:
                logger.error("failed_to_get_access_token", account_id=str(account.id))
                return {"success": False, "error": "auth_failed"}

            # Determine date range: last_sync_at to now
            end_date = date.today()
            if account.last_sync_at:
                start_date = account.last_sync_at.date()
            else:
                # First sync: 7 days back
                start_date = end_date - timedelta(days=7)

            metrics_count = await backfill_service.sync_date_range(
                tenant_id=tenant_uuid,
                account=account,
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                chunk_days=CHUNK_DAYS,
            )

            # Update last_sync_at
            await repo.update_pipeboard_account(
                account_id=account.id,
                last_sync_at=datetime.now(UTC),
                last_sync_error=None,
            )

            logger.info(
                "pipeboard_incremental_sync_complete",
                tenant_id=tenant_id,
                metrics_synced=metrics_count,
            )
            return {
                "success": True,
                "metrics_synced": metrics_count,
                "date_range": f"{start_date} to {end_date}",
            }

        except Exception as e:
            logger.error("pipeboard_incremental_sync_failed", tenant_id=tenant_id, error=str(e))
            await repo.update_pipeboard_account(
                account_id=account.id,
                last_sync_error=str(e),
            )
            raise self.retry(exc=e)


async def _sync_historical(
    self,
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
    pipeboard_platform: Optional[str],
) -> dict:
    """Backfill historical date range (chunked)."""
    from app.db.repositories.pipeboard_repo import PipeboardRepository
    from app.services.pipeboard.sync_service import PipeboardSyncService
    from app.services.pipeboard.backfill_service import PipeboardBackfillService

    async with get_db_context() as db:
        repo = PipeboardRepository(db)
        sync_service = PipeboardSyncService(db)
        backfill_service = PipeboardBackfillService(db)

        tenant_uuid = uuid.UUID(tenant_id)

        # Check account active
        account = await repo.get_active_pipeboard_account(tenant_uuid)
        if not account:
            logger.warning("no_active_account", tenant_id=tenant_id)
            return {"success": False, "error": "no_active_account"}

        try:
            # Get valid access token
            access_token = await sync_service.get_valid_access_token(
                account,
                client_id=settings.PIPEBOARD_CLIENT_ID,
                client_secret=settings.PIPEBOARD_CLIENT_SECRET,
            )
            if not access_token:
                return {"success": False, "error": "auth_failed"}

            # Parse date range
            end_date = date.fromisoformat(date_to) if date_to else date.today()
            start_date = date.fromisoformat(date_from) if date_from else (end_date - timedelta(days=90))

            logger.info(
                "pipeboard_historical_sync_start",
                tenant_id=tenant_id,
                date_range=f"{start_date} to {end_date}",
            )

            # Sync with chunking
            metrics_count = await backfill_service.sync_date_range(
                tenant_id=tenant_uuid,
                account=account,
                access_token=access_token,
                start_date=start_date,
                end_date=end_date,
                chunk_days=CHUNK_DAYS,
                platform_filter=pipeboard_platform,
            )

            logger.info(
                "pipeboard_historical_sync_complete",
                tenant_id=tenant_id,
                metrics_synced=metrics_count,
            )
            return {
                "success": True,
                "metrics_synced": metrics_count,
                "date_range": f"{start_date} to {end_date}",
            }

        except Exception as e:
            logger.error("pipeboard_historical_sync_failed", tenant_id=tenant_id, error=str(e))
            raise self.retry(exc=e)


@celery_app.task(name="pipeboard.daily_sync_all_tenants", bind=True)
def daily_pipeboard_sync_all_tenants(self) -> None:
    """Beat: sync Pipeboard for all active tenants."""
    asyncio.run(_daily_sync_all_tenants())


async def _daily_sync_all_tenants() -> None:
    """Trigger incremental sync for each tenant with active Pipeboard account."""
    from app.db.repositories.pipeboard_repo import PipeboardRepository

    async with get_db_context() as db:
        repo = PipeboardRepository(db)

        accounts = await repo.get_all_active_accounts()
        logger.info("pipeboard_daily_sync_dispatcher_start", account_count=len(accounts))

        for account in accounts:
            # Queue incremental sync for each tenant
            sync_pipeboard_incremental.apply_async(
                args=[str(account.tenant_id)],
                queue="sync",
            )

        logger.info("pipeboard_daily_sync_dispatcher_complete", account_count=len(accounts))
