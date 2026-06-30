"""Google Ads optimization endpoints.

Routes:
  GET  /api/v1/google-ads/optimization/recommendations - list recommendations for a date
  GET  /api/v1/google-ads/optimization/actions - list executed actions for a date
  GET  /api/v1/google-ads/optimization/summary - aggregate stats for dashboard
  POST /api/v1/google-ads/optimization/run - trigger optimization run now
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.db.models import GoogleAdsOptimizationAction, GoogleAdsOptimizationRecommendation
from app.db.repositories.google_ads_optimization_repo import GoogleAdsOptimizationRepository
from app.db.session import get_db
from app.schemas.google_ads_optimization_schemas import (
    ActionResponse,
    OptimizationRunResponse,
    OptimizationSummaryResponse,
    RecommendationResponse,
)
from app.services.google_ads_optimization_sync import GoogleAdsOptimizationSync

logger = structlog.get_logger(__name__)

router = APIRouter()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


@router.get("/recommendations", response_model=list[RecommendationResponse])
async def list_recommendations(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RecommendationResponse]:
    current_user.require_role("owner", "manager", "viewer")
    target_date = date or _today()

    stmt = (
        select(GoogleAdsOptimizationRecommendation)
        .where(
            GoogleAdsOptimizationRecommendation.tenant_id == current_user.tenant_id,
            GoogleAdsOptimizationRecommendation.recommendation_date == target_date,
        )
        .order_by(GoogleAdsOptimizationRecommendation.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        RecommendationResponse(
            id=str(r.id),
            campaign_id=str(r.campaign_id),
            recommendation_date=r.recommendation_date,
            recommendation_type=r.recommendation_type,
            status=r.status,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            entity_name=r.entity_name,
            recommendation_data=r.recommendation_data or {},
            metric_data=r.metric_data or {},
            confidence_score=float(r.confidence_score) if r.confidence_score is not None else None,
            reasoning=r.reasoning,
            executed_at=r.executed_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/actions", response_model=list[ActionResponse])
async def list_actions(
    date: str | None = Query(default=None, description="YYYY-MM-DD; defaults to today"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ActionResponse]:
    current_user.require_role("owner", "manager", "viewer")
    target_date = date or _today()

    repo = GoogleAdsOptimizationRepository(db)
    rows = await repo.get_actions_by_date(current_user.tenant_id, target_date)

    return [
        ActionResponse(
            id=str(a.id),
            campaign_id=str(a.campaign_id),
            recommendation_id=str(a.recommendation_id) if a.recommendation_id else None,
            action_type=a.action_type,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            status=a.status,
            error_message=a.error_message,
            request_data=a.request_data or {},
            response_data=a.response_data,
            action_date=a.action_date,
            executed_at=a.executed_at,
            created_at=a.created_at,
        )
        for a in rows
    ]


@router.get("/summary", response_model=OptimizationSummaryResponse)
async def get_summary(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OptimizationSummaryResponse:
    current_user.require_role("owner", "manager", "viewer")
    tid = current_user.tenant_id

    total_recs = await db.scalar(
        select(func.count()).select_from(GoogleAdsOptimizationRecommendation).where(
            GoogleAdsOptimizationRecommendation.tenant_id == tid
        )
    ) or 0
    total_actions = await db.scalar(
        select(func.count()).select_from(GoogleAdsOptimizationAction).where(
            GoogleAdsOptimizationAction.tenant_id == tid
        )
    ) or 0
    succeeded = await db.scalar(
        select(func.count()).select_from(GoogleAdsOptimizationAction).where(
            GoogleAdsOptimizationAction.tenant_id == tid,
            GoogleAdsOptimizationAction.status == "success",
        )
    ) or 0
    failed = await db.scalar(
        select(func.count()).select_from(GoogleAdsOptimizationAction).where(
            GoogleAdsOptimizationAction.tenant_id == tid,
            GoogleAdsOptimizationAction.status == "failed",
        )
    ) or 0
    last_run = await db.scalar(
        select(func.max(GoogleAdsOptimizationAction.executed_at)).where(
            GoogleAdsOptimizationAction.tenant_id == tid
        )
    )

    # Status: alert if any failures, watch if no recent run, else healthy.
    if failed > 0:
        status = "alert"
    elif last_run is None:
        status = "watch"
    else:
        status = "healthy"

    return OptimizationSummaryResponse(
        total_recommendations=int(total_recs),
        total_actions=int(total_actions),
        actions_succeeded=int(succeeded),
        actions_failed=int(failed),
        last_run_at=last_run.isoformat() if last_run else None,
        status=status,
    )


@router.post("/run", response_model=OptimizationRunResponse)
async def run_optimization(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OptimizationRunResponse:
    """Trigger an optimization run immediately (auto-executes recommendations)."""
    current_user.require_role("owner", "manager")

    sync = GoogleAdsOptimizationSync(db)
    try:
        result = await sync.sync_and_optimize_daily(current_user.tenant_id)
        return OptimizationRunResponse(**result)
    except Exception as e:
        logger.exception("optimization_run_failed", tenant_id=current_user.tenant_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Optimization run failed: {str(e)}")
