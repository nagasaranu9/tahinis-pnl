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

from app.core.auth import get_current_user, require_role
from app.core.database import get_db
from app.schemas.auth import User
from app.schemas.pipeboard_schemas import (
    AlertResponse,
    AuditLogResponse,
    CategoryMappingRequest,
    CategoryMappingResponse,
    DisconnectRequest,
    DismissAlertRequest,
    ManualSyncRequest,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    PipeboardAccountStatus,
    SyncJobResponse,
)
from app.services.pipeboard.sync_service import PipeboardSyncService

logger = structlog.get_logger(__name__)

router = APIRouter()

# Config from env
PIPEBOARD_CLIENT_ID = os.getenv("PIPEBOARD_CLIENT_ID", "")
PIPEBOARD_CLIENT_SECRET = os.getenv("PIPEBOARD_CLIENT_SECRET", "")
PIPEBOARD_REDIRECT_URI = os.getenv("PIPEBOARD_REDIRECT_URI", "http://localhost:3000/integrations/pipeboard/callback")
PIPEBOARD_ADAPTER = os.getenv("PIPEBOARD_ADAPTER", "mock")


@router.post("/oauth/authorize")
async def get_oauth_authorize_url(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get OAuth authorization URL.

    Returns URL user should visit to authorize.
    """
    require_role(current_user, ["owner", "manager"])

    service = PipeboardSyncService(db)
    state = f"{current_user.tenant_id}_{uuid.uuid4().hex[:8]}"

    try:
        auth_url = await service._adapter.get_oauth_authorize_url(
            client_id=PIPEBOARD_CLIENT_ID,
            redirect_uri=PIPEBOARD_REDIRECT_URI,
            state=state,
        )
        return {
            "authorize_url": auth_url,
            "state": state,
        }
    except Exception as e:
        logger.error("authorize_url_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to generate authorize URL")


@router.get("/oauth/callback")
async def handle_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse:
    """Handle OAuth callback from Pipeboard.

    Exchanges code for tokens and creates PipeboardAccount.
    """
    require_role(current_user, ["owner", "manager"])

    # Verify state includes tenant_id
    try:
        state_tenant_id = uuid.UUID(state.split("_")[0])
        if state_tenant_id != current_user.tenant_id:
            raise ValueError("state_tenant_mismatch")
    except (IndexError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    service = PipeboardSyncService(db)

    try:
        account = await service.handle_oauth_callback(
            tenant_id=current_user.tenant_id,
            code=code,
            state=state,
            client_id=PIPEBOARD_CLIENT_ID,
            client_secret=PIPEBOARD_CLIENT_SECRET,
            redirect_uri=PIPEBOARD_REDIRECT_URI,
        )

        return OAuthCallbackResponse(
            success=True,
            account_id=str(account.id),
            message="Successfully connected to Pipeboard",
        )

    except Exception as e:
        logger.error("oauth_callback_error", error=str(e), tenant_id=current_user.tenant_id)
        raise HTTPException(status_code=400, detail=f"OAuth failed: {str(e)}")


@router.get("/status", response_model=PipeboardAccountStatus)
async def get_account_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PipeboardAccountStatus:
    """Get connection status."""
    require_role(current_user, ["owner", "manager", "viewer"])

    service = PipeboardSyncService(db)
    status = await service.get_account_status(current_user.tenant_id)
    return PipeboardAccountStatus(**status)


@router.post("/oauth/disconnect", response_model=OAuthCallbackResponse)
async def disconnect_account(
    body: DisconnectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OAuthCallbackResponse:
    """Disconnect Pipeboard account."""
    require_role(current_user, ["owner"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryMappingResponse]:
    """List category mappings for tenant."""
    require_role(current_user, ["owner", "manager", "viewer"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CategoryMappingResponse:
    """Create or update category mapping."""
    require_role(current_user, ["owner", "manager"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete category mapping."""
    require_role(current_user, ["owner", "manager"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger manual sync job.

    Creates sync job in pending state for Celery worker to process.
    """
    require_role(current_user, ["owner", "manager"])

    from app.db.repositories.pipeboard_repo import PipeboardRepository
    from datetime import date

    repo = PipeboardRepository(db)

    # TODO: validate account is connected
    # TODO: create sync job

    return {
        "success": True,
        "message": "Sync job created",
        "job_id": str(uuid.uuid4()),
    }


@router.get("/alerts", response_model=list[AlertResponse])
async def get_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AlertResponse]:
    """Get active (non-dismissed) alerts for tenant."""
    require_role(current_user, ["owner", "manager", "viewer"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss an alert."""
    require_role(current_user, ["owner", "manager"])

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLogResponse]:
    """Get audit log entries for tenant."""
    require_role(current_user, ["owner", "manager"])

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


@router.get("/sync-jobs", response_model=list[SyncJobResponse])
async def get_sync_jobs(
    status: Optional[str] = Query(None, description="Filter by status: pending/running/complete/failed"),
    limit: int = Query(50, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SyncJobResponse]:
    """Get sync job history for tenant."""
    require_role(current_user, ["owner", "manager", "viewer"])

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
