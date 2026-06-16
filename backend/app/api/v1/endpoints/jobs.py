"""Job runs monitoring endpoint."""
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import and_, func, select

from app.core.deps import CurrentUserDep
from app.db.models.job_run import JobRun
from app.db.session import AsyncSessionDep
from app.schemas.common import PaginatedMeta, PaginatedResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


class JobRunResponse:
    pass


from pydantic import BaseModel, ConfigDict
from decimal import Decimal
from typing import Any, Optional


class JobRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    celery_task_id: str
    task_name: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[Decimal] = None
    error_message: Optional[str] = None
    result_summary: Optional[dict[str, Any]] = None
    created_at: datetime


@router.get("", response_model=PaginatedResponse[JobRunOut])
async def list_job_runs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    status: str | None = Query(None, description="Filter by status: pending|running|success|failure|retry"),
    task_name: str | None = Query(None, description="Filter by task name substring"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """List job runs for this tenant, newest first."""
    conditions = [JobRun.tenant_id == user.tenant_id]
    if status:
        conditions.append(JobRun.status == status)
    if task_name:
        conditions.append(JobRun.task_name.ilike(f"%{task_name}%"))

    total_q = select(func.count()).select_from(JobRun).where(and_(*conditions))
    total = (await db.execute(total_q)).scalar_one()

    rows_q = (
        select(JobRun)
        .where(and_(*conditions))
        .order_by(JobRun.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    rows = (await db.execute(rows_q)).scalars().all()

    return {
        "data": [JobRunOut.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.get("/summary", response_model=dict)
async def job_runs_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    """Counts by status for dashboard widget."""
    stmt = (
        select(JobRun.status, func.count().label("cnt"))
        .where(JobRun.tenant_id == user.tenant_id)
        .group_by(JobRun.status)
    )
    rows = (await db.execute(stmt)).all()
    counts = {r.status: r.cnt for r in rows}
    return {
        "total": sum(counts.values()),
        "running": counts.get("running", 0),
        "success": counts.get("success", 0),
        "failure": counts.get("failure", 0),
        "retry": counts.get("retry", 0),
    }
