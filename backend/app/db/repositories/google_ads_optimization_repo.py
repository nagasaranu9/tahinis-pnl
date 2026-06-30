"""Repository for Google Ads optimization data access."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GoogleAdsOptimizationRecommendation, GoogleAdsOptimizationAction


class GoogleAdsOptimizationRepository:
    """Data access layer for Google Ads optimization."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_recommendation(
        self,
        tenant_id: uuid.UUID,
        campaign_id: uuid.UUID,
        recommendation_date: str,
        recommendation_type: str,
        entity_type: str,
        entity_id: str,
        entity_name: Optional[str],
        recommendation_data: dict,
        metric_data: dict,
        confidence_score: Optional[Decimal] = None,
        reasoning: Optional[str] = None,
    ) -> GoogleAdsOptimizationRecommendation:
        """Create optimization recommendation."""
        rec = GoogleAdsOptimizationRecommendation(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            recommendation_date=recommendation_date,
            recommendation_type=recommendation_type,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            recommendation_data=recommendation_data,
            metric_data=metric_data,
            confidence_score=confidence_score,
            reasoning=reasoning,
            status="pending",
        )
        self.session.add(rec)
        await self.session.flush()
        return rec

    async def get_pending_recommendations(
        self, tenant_id: uuid.UUID, recommendation_date: str
    ) -> list[GoogleAdsOptimizationRecommendation]:
        """Get all pending recommendations for date."""
        stmt = select(GoogleAdsOptimizationRecommendation).where(
            and_(
                GoogleAdsOptimizationRecommendation.tenant_id == tenant_id,
                GoogleAdsOptimizationRecommendation.recommendation_date == recommendation_date,
                GoogleAdsOptimizationRecommendation.status == "pending",
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_recommendation_executed(
        self, recommendation_id: uuid.UUID, executed_at: datetime
    ) -> None:
        """Mark recommendation as executed."""
        rec = await self.session.get(GoogleAdsOptimizationRecommendation, recommendation_id)
        if rec:
            rec.status = "executed"
            rec.executed_at = executed_at
            await self.session.flush()

    async def create_action(
        self,
        tenant_id: uuid.UUID,
        campaign_id: uuid.UUID,
        action_type: str,
        entity_type: str,
        entity_id: str,
        request_data: dict,
        action_date: str,
        recommendation_id: Optional[uuid.UUID] = None,
    ) -> GoogleAdsOptimizationAction:
        """Create optimization action."""
        action = GoogleAdsOptimizationAction(
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            recommendation_id=recommendation_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            request_data=request_data,
            action_date=action_date,
            status="pending",
        )
        self.session.add(action)
        await self.session.flush()
        return action

    async def update_action_status(
        self,
        action_id: uuid.UUID,
        status: str,
        response_data: Optional[dict] = None,
        error_message: Optional[str] = None,
        executed_at: Optional[datetime] = None,
    ) -> None:
        """Update action execution status."""
        action = await self.session.get(GoogleAdsOptimizationAction, action_id)
        if action:
            action.status = status
            if response_data is not None:
                action.response_data = response_data
            if error_message is not None:
                action.error_message = error_message
            if executed_at is not None:
                action.executed_at = executed_at
            await self.session.flush()

    async def get_actions_by_date(
        self, tenant_id: uuid.UUID, action_date: str
    ) -> list[GoogleAdsOptimizationAction]:
        """Get actions for date."""
        stmt = select(GoogleAdsOptimizationAction).where(
            and_(
                GoogleAdsOptimizationAction.tenant_id == tenant_id,
                GoogleAdsOptimizationAction.action_date == action_date,
            )
        ).order_by(desc(GoogleAdsOptimizationAction.created_at))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_pending_actions(self, tenant_id: uuid.UUID) -> list[GoogleAdsOptimizationAction]:
        """Get all pending actions."""
        stmt = select(GoogleAdsOptimizationAction).where(
            and_(
                GoogleAdsOptimizationAction.tenant_id == tenant_id,
                GoogleAdsOptimizationAction.status == "pending",
            )
        ).order_by(GoogleAdsOptimizationAction.created_at)
        result = await self.session.execute(stmt)
        return result.scalars().all()
