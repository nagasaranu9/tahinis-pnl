"""Pipeboard OAuth and management endpoints.

Routes:
  POST /api/v1/integrations/pipeboard/oauth/authorize - get OAuth URL
  GET  /api/v1/integrations/pipeboard/oauth/callback - handle OAuth callback
  POST /api/v1/integrations/pipeboard/oauth/disconnect - revoke access
  GET  /api/v1/integrations/pipeboard/status - check connection
  GET  /api/v1/integrations/pipeboard/category-mappings - list mappings
  POST /api/v1/integrations/pipeboard/category-mappings - create mapping
  POST /api/v1/integrations/pipeboard/sync/manual - trigger manual sync
"""
from __future__ import annotations

import os
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.pipeboard_schemas import (
    AlertResponse,
    AuditLogResponse,
    CategoryMappingRequest,
    CategoryMappingResponse,
    ConnectTokenRequest,
    DisconnectRequest,
    DismissAlertRequest,
    ManualSyncRequest,
    OAuthCallbackResponse,
    PipeboardAccountStatus,
    SyncJobResponse,
)
from app.services.pipeboard.sync_service import PipeboardSyncService

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.post("/connect", response_model=OAuthCallbackResponse)
async def connect_with_token(
    body: ConnectTokenRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse:
    """Connect Pipeboard with an API token.

    Token is validated against the platform's MCP server (list accounts),
    then stored encrypted per tenant. Get a token at https://pipeboard.co/api-tokens.
    """
    current_user.require_role("owner", "manager")

    service = PipeboardSyncService(db)
    try:
        account = await service.connect_with_token(
            tenant_id=current_user.tenant_id,
            api_token=body.api_token,
            platform=body.platform or "google_ads",
        )
        return OAuthCallbackResponse(
            success=True,
            account_id=str(account.id),
            message="Successfully connected to Pipeboard",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("pipeboard_connect_error", error=str(e), tenant_id=current_user.tenant_id)
        raise HTTPException(status_code=400, detail=f"Connect failed: {str(e)}")


@router.get("/status", response_model=PipeboardAccountStatus)
async def get_account_status(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipeboardAccountStatus:
    """Get connection status."""
    current_user.require_role("owner", "manager", "viewer")

    service = PipeboardSyncService(db)
    status = await service.get_account_status(current_user.tenant_id)
    return PipeboardAccountStatus(**status)


@router.post("/oauth/disconnect", response_model=OAuthCallbackResponse)
async def disconnect_account(
    body: DisconnectRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse:
    """Disconnect Pipeboard account."""
    current_user.require_role("owner")

    if not body.confirm:
        raise HTTPException(status_code=400, detail="Disconnect must be confirmed")

    service = PipeboardSyncService(db)
    status = await service.get_account_status(current_user.tenant_id)

    if not status["connected"] or not status["account_id"]:
        raise HTTPException(status_code=404, detail="No connected account")

    try:
        await service.disconnect_account(
            tenant_id=current_user.tenant_id,
            account_id=uuid.UUID(status["account_id"]),
        )
        return OAuthCallbackResponse(
            success=True,
            account_id=status["account_id"],
            message="Account disconnected successfully",
        )
    except Exception as e:
        logger.error("disconnect_failed", error=str(e), tenant_id=current_user.tenant_id)
        raise HTTPException(status_code=500, detail="Failed to disconnect")


@router.get("/category-mappings")
async def list_category_mappings(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryMappingResponse]:
    """List category mappings for tenant."""
    current_user.require_role("owner", "manager", "viewer")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)
    mappings = await repo.get_category_mappings_for_tenant(current_user.tenant_id)

    return [
        CategoryMappingResponse(
            id=str(mapping.id),
            pipeboard_platform=mapping.pipeboard_platform,
            pipeboard_campaign_type=mapping.pipeboard_campaign_type,
            expense_category=mapping.expense_category,
            created_at=mapping.created_at,
            updated_at=mapping.updated_at,
        )
        for mapping in mappings
    ]


@router.post("/category-mappings", response_model=CategoryMappingResponse)
async def create_category_mapping(
    body: CategoryMappingRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryMappingResponse:
    """Create or update category mapping."""
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)

    try:
        mapping = await repo.upsert_category_mapping(
            tenant_id=current_user.tenant_id,
            pipeboard_platform=body.pipeboard_platform,
            pipeboard_campaign_type=body.pipeboard_campaign_type,
            expense_category=body.expense_category,
        )

        return CategoryMappingResponse(
            id=str(mapping.id),
            pipeboard_platform=mapping.pipeboard_platform,
            pipeboard_campaign_type=mapping.pipeboard_campaign_type,
            expense_category=mapping.expense_category,
            created_at=mapping.created_at,
            updated_at=mapping.updated_at,
        )

    except Exception as e:
        logger.error("category_mapping_failed", error=str(e), tenant_id=current_user.tenant_id)
        raise HTTPException(status_code=400, detail=f"Failed to create mapping: {str(e)}")


@router.delete("/category-mappings/{mapping_id}")
async def delete_category_mapping(
    mapping_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete category mapping."""
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)

    try:
        await repo.delete_category_mapping(
            mapping_id=uuid.UUID(mapping_id),
            tenant_id=current_user.tenant_id,
        )
        return {"success": True, "message": "Mapping deleted"}
    except Exception as e:
        logger.error("delete_mapping_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to delete mapping: {str(e)}")


@router.post("/sync/manual")
async def trigger_manual_sync(
    body: ManualSyncRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger manual sync job.

    Creates sync job in pending state for Celery worker to process.
    """
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository
    from app.workers.tasks.pipeboard_tasks import sync_pipeboard_historical

    repo = PipeboardRepository(db)

    # Validate account is connected
    account = await repo.get_active_pipeboard_account(current_user.tenant_id)
    if not account:
        raise HTTPException(status_code=400, detail="No active Pipeboard account")

    # Create sync job record
    job = await repo.create_sync_job(
        tenant_id=current_user.tenant_id,
        job_type="historical",
        pipeboard_platform=body.pipeboard_platform,
        date_from=body.date_from,
        date_to=body.date_to,
        triggered_by=current_user.user_id,
    )

    # Queue Celery task
    sync_pipeboard_historical.apply_async(
        args=[
            str(current_user.tenant_id),
            body.date_from,
            body.date_to,
            body.pipeboard_platform,
        ],
        queue="sync",
    )

    logger.info(
        "manual_sync_triggered",
        tenant_id=current_user.tenant_id,
        job_id=str(job.id),
        date_range=f"{body.date_from} to {body.date_to}",
    )

    return {
        "success": True,
        "message": "Sync job created",
        "job_id": str(job.id),
    }


@router.get("/alerts", response_model=list[AlertResponse])
async def get_alerts(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    """Get active (non-dismissed) alerts for tenant."""
    current_user.require_role("owner", "manager", "viewer")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)
    alerts = await repo.get_active_alerts(current_user.tenant_id)

    return [
        AlertResponse(
            id=str(alert.id),
            alert_type=alert.alert_type,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            is_dismissed=alert.is_dismissed,
            created_at=alert.created_at,
        )
        for alert in alerts
    ]


@router.post("/alerts/dismiss")
async def dismiss_alert(
    body: DismissAlertRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss an alert."""
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)

    try:
        await repo.dismiss_alert(
            alert_id=uuid.UUID(body.alert_id),
            dismissed_by=current_user.user_id,
        )
        return {"success": True, "message": "Alert dismissed"}
    except Exception as e:
        logger.error("dismiss_alert_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to dismiss alert: {str(e)}")


@router.get("/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    limit: int = Query(100, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """Get audit log entries for tenant."""
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)
    logs = await repo.get_audit_logs(current_user.tenant_id, limit=limit)

    return [
        AuditLogResponse(
            id=str(log.id),
            event_type=log.event_type,
            severity=log.severity,
            message=log.message,
            error_detail=log.error_detail,
            account_id=str(log.account_id) if log.account_id else None,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.delete("/sync-jobs/{job_id}")
async def delete_sync_job(
    job_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a sync job record (any status). Owner/manager only."""
    current_user.require_role("owner", "manager")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)
    deleted = await repo.delete_sync_job(current_user.tenant_id, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Sync job not found")
    return {"success": True}


@router.get("/sync-jobs", response_model=list[SyncJobResponse])
async def get_sync_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending/running/complete/failed"),
    limit: int = Query(50, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SyncJobResponse]:
    """Get sync job history for tenant."""
    current_user.require_role("owner", "manager", "viewer")

    from app.db.repositories.pipeboard_repo import PipeboardRepository

    repo = PipeboardRepository(db)
    jobs = await repo.get_sync_jobs(current_user.tenant_id, status=status, limit=limit)

    return [
        SyncJobResponse(
            id=str(job.id),
            job_type=job.job_type,
            status=job.status,
            pipeboard_platform=job.pipeboard_platform,
            date_from=job.date_from,
            date_to=job.date_to,
            metrics_synced=job.metrics_synced,
            campaigns_synced=job.campaigns_synced,
            error_message=job.error_message,
            started_at=job.started_at,
            completed_at=job.completed_at,
            triggered_by=str(job.triggered_by) if job.triggered_by else None,
        )
        for job in jobs
    ]
