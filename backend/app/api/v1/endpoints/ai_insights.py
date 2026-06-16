"""AI Insights endpoints."""
import uuid

import structlog
from fastapi import APIRouter, Query

from app.core.deps import CurrentUserDep, ManagerDep
from app.db.repositories.ai_insight_repo import AIInsightRepository
from app.db.session import AsyncSessionDep
from app.schemas.ai_insight import (
    AIInsightResponse,
    DismissInsightRequest,
    FeedbackRequest,
    GenerateInsightsRequest,
)
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("", response_model=PaginatedResponse[AIInsightResponse])
async def list_insights(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    insight_type: str | None = Query(None),
    include_dismissed: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    repo = AIInsightRepository(db)
    rows, total = await repo.list_insights(
        tenant_id=user.tenant_id,
        location_id=location_id,
        insight_type=insight_type,
        include_dismissed=include_dismissed,
        page=page,
        limit=limit,
    )
    return {
        "data": [AIInsightResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.get("/{insight_id}", response_model=APIResponse[AIInsightResponse])
async def get_insight(
    insight_id: uuid.UUID,
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    repo = AIInsightRepository(db)
    insight = await repo.get(user.tenant_id, insight_id)
    return {"data": AIInsightResponse.model_validate(insight), "errors": None}


@router.post("/generate", status_code=202)
async def generate_insights(
    body: GenerateInsightsRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    """Dispatch on-demand insight generation task. Returns 202 — insight saved async."""
    from app.workers.tasks.ai_insights import generate_insights_on_demand
    generate_insights_on_demand.apply_async(
        kwargs={
            "tenant_id": str(user.tenant_id),
            "insight_type": body.insight_type,
            "period_start": body.period_start,
            "period_end": body.period_end,
            "location_id": str(body.location_id) if body.location_id else None,
        },
        queue="ai",
    )
    logger.info("on_demand_insight_queued", tenant_id=str(user.tenant_id), insight_type=body.insight_type)
    return {"data": {"status": "queued"}, "errors": None}


@router.post("/{insight_id}/dismiss", response_model=APIResponse[AIInsightResponse])
async def dismiss_insight(
    insight_id: uuid.UUID,
    _body: DismissInsightRequest,
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    repo = AIInsightRepository(db)
    insight = await repo.dismiss(user.tenant_id, insight_id, dismissed_by=user.user_id)
    await db.commit()
    return {"data": AIInsightResponse.model_validate(insight), "errors": None}


@router.post("/{insight_id}/feedback", response_model=APIResponse[AIInsightResponse])
async def submit_feedback(
    insight_id: uuid.UUID,
    body: FeedbackRequest,
    user: CurrentUserDep,
    db: AsyncSessionDep,
) -> dict:
    repo = AIInsightRepository(db)
    insight = await repo.record_feedback(user.tenant_id, insight_id, body.is_helpful)
    await db.commit()
    return {"data": AIInsightResponse.model_validate(insight), "errors": None}
