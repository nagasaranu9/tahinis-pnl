"""Google Ads optimization Celery tasks.

optimize_google_ads — daily optimization sync and recommendation execution
optimize_google_ads_all_tenants — Beat entry (runs for all tenants daily)
"""
import asyncio
import uuid

import structlog

from app.db.session import get_db_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="google_ads.optimize_daily",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    queue="sync",
)
def optimize_google_ads(
    self,
    tenant_id: str,
) -> dict:
    """Run daily Google Ads optimization for a tenant."""
    return asyncio.run(_optimize_google_ads(self, tenant_id))


@celery_app.task(
    name="google_ads.optimize_all_tenants",
    bind=True,
    max_retries=1,
    queue="sync",
)
def optimize_google_ads_all_tenants(self) -> dict:
    """Run daily optimization for all tenants with active Pipeboard accounts."""
    return asyncio.run(_optimize_all_tenants())


async def _optimize_google_ads(self, tenant_id: str) -> dict:
    """Run optimization sync for a single tenant."""
    from app.services.google_ads_optimization_sync import GoogleAdsOptimizationSync

    async with get_db_context() as db:
        sync = GoogleAdsOptimizationSync(db)
        tenant_uuid = uuid.UUID(tenant_id)

        try:
            result = await sync.sync_and_optimize_daily(tenant_uuid)
            logger.info(
                "google_ads_optimization_complete",
                tenant_id=tenant_id,
                recommendations=result.get("recommendations_generated", 0),
                actions=result.get("actions_executed", 0),
            )
            return result
        except Exception as e:
            logger.exception("google_ads_optimization_failed", tenant_id=tenant_id, error=str(e))
            self.retry(exc=e)
            return {"success": False, "error": str(e), "tenant_id": tenant_id}


async def _optimize_all_tenants() -> dict:
    """Dispatch optimization jobs for all active tenants."""
    from app.db.repositories.pipeboard_repo import PipeboardRepository

    async with get_db_context() as db:
        repo = PipeboardRepository(db)

        try:
            # Get all tenants with active Pipeboard accounts
            accounts = await repo.get_all_active_accounts()

            if not accounts:
                logger.info("no_active_pipeboard_accounts")
                return {"success": True, "tenants_processed": 0}

            # Deduplicate by tenant_id
            tenant_ids = {str(acc.tenant_id) for acc in accounts}

            # Dispatch a task for each tenant
            for tenant_id in tenant_ids:
                optimize_google_ads.delay(tenant_id)
                logger.info("dispatched_optimization_task", tenant_id=tenant_id)

            logger.info("optimization_dispatch_complete", count=len(tenant_ids))
            return {"success": True, "tenants_processed": len(tenant_ids)}

        except Exception as e:
            logger.exception("failed_to_dispatch_optimization_tasks", error=str(e))
            return {"success": False, "error": str(e)}
