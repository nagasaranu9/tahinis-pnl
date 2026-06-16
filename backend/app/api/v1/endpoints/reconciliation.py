import uuid

import structlog
from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, ManagerDep
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.reconciliation_repo import ReconciliationRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.reconciliation import (
    ReconciliationFlagResponse,
    ReconciliationRunRequest,
    ReconciliationRunResponse,
    ResolveFlagRequest,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.post("/runs", response_model=APIResponse[ReconciliationRunResponse], status_code=202)
async def trigger_reconciliation(
    body: ReconciliationRunRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    repo = ReconciliationRepository(db)
    run = await repo.create_run(
        tenant_id=user.tenant_id,
        period_start=body.period_start,
        period_end=body.period_end,
        triggered_by=user.user_id,
        location_id=body.location_id,
    )
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="reconciliation.run_triggered",
        user_id=user.user_id,
        entity_type="reconciliation_run",
        entity_id=run.id,
        new_value={"period_start": body.period_start.isoformat(), "period_end": body.period_end.isoformat()},
    )
    await db.commit()

    from app.workers.tasks.reconciliation import run_reconciliation
    run_reconciliation.apply_async(
        kwargs={
            "run_id": str(run.id),
            "tenant_id": str(user.tenant_id),
            "period_start": body.period_start.isoformat(),
            "period_end": body.period_end.isoformat(),
            "location_id": str(body.location_id) if body.location_id else None,
        },
        queue="default",
    )
    logger.info("reconciliation_triggered", run_id=str(run.id), by=str(user.user_id))
    return {"data": ReconciliationRunResponse.model_validate(run), "errors": None}


@router.get("/runs", response_model=PaginatedResponse[ReconciliationRunResponse])
async def list_runs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    repo = ReconciliationRepository(db)
    rows, total = await repo.list_runs(
        tenant_id=user.tenant_id,
        location_id=location_id,
        page=page,
        limit=limit,
    )
    return {
        "data": [ReconciliationRunResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.get("/runs/{run_id}", response_model=APIResponse[ReconciliationRunResponse])
async def get_run(run_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = ReconciliationRepository(db)
    run = await repo.get_run(user.tenant_id, run_id)
    return {"data": ReconciliationRunResponse.model_validate(run), "errors": None}


@router.get("/flags", response_model=PaginatedResponse[ReconciliationFlagResponse])
async def list_flags(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    run_id: uuid.UUID | None = Query(None),
    flag_type: str | None = Query(None),
    unresolved_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    repo = ReconciliationRepository(db)
    rows, total = await repo.list_flags(
        tenant_id=user.tenant_id,
        run_id=run_id,
        flag_type=flag_type,
        unresolved_only=unresolved_only,
        page=page,
        limit=limit,
    )
    return {
        "data": [ReconciliationFlagResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.post("/flags/{flag_id}/resolve", response_model=APIResponse[ReconciliationFlagResponse])
async def resolve_flag(
    flag_id: uuid.UUID,
    body: ResolveFlagRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    repo = ReconciliationRepository(db)
    flag = await repo.resolve_flag(
        tenant_id=user.tenant_id,
        flag_id=flag_id,
        resolved_by=user.user_id,
        resolution_note=body.resolution_note,
    )
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="reconciliation.flag_resolved",
        user_id=user.user_id,
        entity_type="reconciliation_flag",
        entity_id=flag_id,
        new_value={"resolution_note": body.resolution_note},
    )
    await db.commit()
    logger.info("flag_resolved", flag_id=str(flag_id), by=str(user.user_id))
    return {"data": ReconciliationFlagResponse.model_validate(flag), "errors": None}
