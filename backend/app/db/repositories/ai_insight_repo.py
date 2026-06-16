"""AI Insight repository."""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.ai_insight import AIInsight
from app.services.ai.insight_service import InsightResult


class AIInsightRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        tenant_id: uuid.UUID,
        result: InsightResult,
        period_start: str | None = None,
        period_end: str | None = None,
        location_id: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        expense_id: uuid.UUID | None = None,
        reconciliation_run_id: uuid.UUID | None = None,
    ) -> AIInsight:
        insight = AIInsight(
            tenant_id=tenant_id,
            location_id=location_id,
            insight_type=result.insight_type,
            severity=result.severity,
            title=result.title,
            summary=result.summary,
            explanation=result.explanation,
            confidence_score=result.confidence_score,
            period_start=period_start,
            period_end=period_end,
            document_id=document_id,
            expense_id=expense_id,
            reconciliation_run_id=reconciliation_run_id,
            model_id=result.model_id,
        )
        self._db.add(insight)
        await self._db.flush()
        return insight

    async def get(self, tenant_id: uuid.UUID, insight_id: uuid.UUID) -> AIInsight:
        row = await self._db.execute(
            select(AIInsight).where(
                and_(AIInsight.tenant_id == tenant_id, AIInsight.id == insight_id)
            )
        )
        insight = row.scalar_one_or_none()
        if insight is None:
            raise NotFoundError(f"AIInsight {insight_id} not found")
        return insight

    async def list_insights(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        insight_type: str | None = None,
        include_dismissed: bool = False,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[AIInsight], int]:
        conds = [AIInsight.tenant_id == tenant_id]
        if location_id:
            conds.append(AIInsight.location_id == location_id)
        if insight_type:
            conds.append(AIInsight.insight_type == insight_type)
        if not include_dismissed:
            conds.append(AIInsight.is_dismissed == False)  # noqa: E712

        total = (
            await self._db.execute(
                select(func.count()).select_from(AIInsight).where(and_(*conds))
            )
        ).scalar_one()

        rows = await self._db.execute(
            select(AIInsight)
            .where(and_(*conds))
            .order_by(AIInsight.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), total

    async def dismiss(self, tenant_id: uuid.UUID, insight_id: uuid.UUID, dismissed_by: uuid.UUID) -> AIInsight:
        insight = await self.get(tenant_id, insight_id)
        insight.is_dismissed = True
        insight.dismissed_by = dismissed_by
        await self._db.flush()
        return insight

    async def record_feedback(self, tenant_id: uuid.UUID, insight_id: uuid.UUID, is_helpful: bool) -> AIInsight:
        insight = await self.get(tenant_id, insight_id)
        insight.is_helpful = is_helpful
        await self._db.flush()
        return insight
