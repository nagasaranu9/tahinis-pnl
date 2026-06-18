import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, ManagerDep, OwnerDep
from app.core.exceptions import NotFoundError
from app.core.security import encrypt_value
from app.db.models.integration import IntegrationCredential
from app.db.repositories.toast_repo import ToastRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.toast import (
    ManualSyncRequest,
    ToastConnectRequest,
    ToastConnectResponse,
    ToastSyncJobResponse,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/connect", response_model=APIResponse[ToastConnectResponse])
async def connect_toast(
    body: ToastConnectRequest,
    user: OwnerDep,
    db: AsyncSessionDep,
) -> dict:
    """
    Save encrypted Toast credentials for a location.
    Triggers historical import automatically on first connect.
    """
    # Store credentials encrypted in integration_credentials
    cred = IntegrationCredential(
        tenant_id=user.tenant_id,
        location_id=body.location_id,
        provider="toast",
        access_token_encrypted=encrypt_value(body.client_id),
        refresh_token_encrypted=encrypt_value(body.client_secret),
    )
    db.add(cred)
    await db.flush()

    repo = ToastRepository(db)
    config = await repo.upsert_sync_config(
        tenant_id=user.tenant_id,
        location_id=body.location_id,
        integration_credential_id=cred.id,
        toast_restaurant_guid=body.toast_restaurant_guid,
        historical_import_from=body.historical_import_from,
    )
    await db.commit()

    # Kick off historical import if this is first-time connect
    if not config.historical_import_complete:
        job = await repo.create_sync_job(
            tenant_id=user.tenant_id,
            location_id=body.location_id,
            job_type="historical",
            date_from=config.historical_import_from,
            date_to=datetime.now(UTC),
            triggered_by=user.user_id,
        )
        await db.commit()

        # Enqueue is best-effort: if the broker (Redis) is down, the credentials
        # are already saved and the job row exists, so the connect must still
        # succeed. A scheduled sync / manual retry can pick the job up later.
        try:
            from app.workers.tasks.toast_sync import toast_historical_import
            toast_historical_import.apply_async(
                args=[str(user.tenant_id), str(body.location_id), str(job.id)],
                queue="sync",
            )
            logger.info("toast_historical_import_queued", location_id=str(body.location_id))
        except Exception as exc:
            logger.error(
                "toast_historical_import_enqueue_failed",
                location_id=str(body.location_id),
                job_id=str(job.id),
                error_type=type(exc).__name__,
                error=str(exc),
            )

    return {"data": ToastConnectResponse.model_validate(config), "errors": None}


@router.get("/status", response_model=APIResponse[ToastConnectResponse])
async def get_toast_status(
    location_id: uuid.UUID,
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    repo = ToastRepository(db)
    config = await repo.get_sync_config(user.tenant_id, location_id)
    if not config:
        raise NotFoundError("Toast not connected for this location")
    return {"data": ToastConnectResponse.model_validate(config), "errors": None}


@router.post("/sync", response_model=APIResponse[ToastSyncJobResponse])
async def trigger_manual_sync(
    body: ManualSyncRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    repo = ToastRepository(db)
    config = await repo.get_sync_config(user.tenant_id, body.location_id)
    if not config or not config.is_active:
        raise NotFoundError("Toast not connected for this location")

    job = await repo.create_sync_job(
        tenant_id=user.tenant_id,
        location_id=body.location_id,
        job_type=body.sync_type,
        date_from=body.date_from,
        date_to=body.date_to or datetime.now(UTC),
        triggered_by=user.user_id,
    )
    await db.commit()

    if body.sync_type == "historical":
        from app.workers.tasks.toast_sync import toast_historical_import
        toast_historical_import.apply_async(
            args=[str(user.tenant_id), str(body.location_id), str(job.id)],
            queue="sync",
        )
    else:
        from app.workers.tasks.toast_sync import toast_incremental_sync
        toast_incremental_sync.apply_async(
            args=[str(user.tenant_id), str(body.location_id), str(job.id)],
            queue="sync",
        )

    logger.info(
        "toast_manual_sync_queued",
        job_id=str(job.id),
        sync_type=body.sync_type,
        triggered_by=str(user.user_id),
    )
    return {"data": ToastSyncJobResponse.model_validate(job), "errors": None}


@router.get("/sync-jobs", response_model=PaginatedResponse[ToastSyncJobResponse])
async def list_sync_jobs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    repo = ToastRepository(db)
    offset = (page - 1) * limit
    jobs, total = await repo.list_sync_jobs(
        tenant_id=user.tenant_id,
        location_id=location_id,
        limit=limit,
        offset=offset,
    )
    return {
        "data": [ToastSyncJobResponse.model_validate(j) for j in jobs],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.delete("/disconnect", response_model=APIResponse[None])
async def disconnect_toast(
    location_id: uuid.UUID,
    user: OwnerDep,
    db: AsyncSessionDep,
) -> dict:
    from sqlalchemy import update
    from app.db.models.toast import ToastSyncConfig

    await db.execute(
        update(ToastSyncConfig)
        .where(
            ToastSyncConfig.tenant_id == user.tenant_id,
            ToastSyncConfig.location_id == location_id,
        )
        .values(is_active=False)
    )
    await db.commit()
    logger.info("toast_disconnected", location_id=str(location_id), by=str(user.user_id))
    return {"data": None, "errors": None}
