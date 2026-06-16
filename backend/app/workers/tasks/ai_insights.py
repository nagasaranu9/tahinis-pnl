"""AI Insight generation Celery tasks.

generate_pnl_insights          — triggered after monthly P&L snapshot.
generate_reconciliation_insights — triggered after reconciliation run completes.
generate_insights_on_demand    — API-triggered, any insight type.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import structlog

from app.db.session import get_db_context
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(name="ai.generate_pnl_insights", bind=True, max_retries=2, default_retry_delay=120)
def generate_pnl_insights(
    self,
    tenant_id: str,
    period_start: str,
    period_end: str,
    location_id: str | None = None,
) -> None:
    asyncio.run(_generate_pnl(tenant_id, period_start, period_end, location_id))


async def _generate_pnl(
    tenant_id: str,
    period_start: str,
    period_end: str,
    location_id: str | None,
) -> None:
    from app.services.pnl.calculator import PnLCalculator
    from app.services.ai.insight_service import AIInsightService, InsightContextBuilder
    from app.db.repositories.ai_insight_repo import AIInsightRepository

    t_id = uuid.UUID(tenant_id)
    loc_id = uuid.UUID(location_id) if location_id else None
    start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(period_end).replace(tzinfo=timezone.utc)

    async with get_db_context() as db:
        calculator = PnLCalculator(db)
        report = await calculator.compute(t_id, start_dt, end_dt, loc_id)

        svc = AIInsightService()
        repo = AIInsightRepository(db)

        # Generate pnl_summary insight
        pnl_ctx = InsightContextBuilder.pnl_summary(report)
        pnl_result = svc.generate("pnl_summary", pnl_ctx, period_start, period_end)
        await repo.create(t_id, pnl_result, period_start, period_end, loc_id)

        # Generate category_analysis insight
        cat_ctx = InsightContextBuilder.category_analysis(report)
        cat_result = svc.generate("category_analysis", cat_ctx, period_start, period_end)
        await repo.create(t_id, cat_result, period_start, period_end, loc_id)

        await db.commit()

    logger.info("pnl_insights_generated", tenant_id=tenant_id, period_start=period_start)


@celery_app.task(name="ai.generate_reconciliation_insights", bind=True, max_retries=2, default_retry_delay=120)
def generate_reconciliation_insights(
    self,
    tenant_id: str,
    run_id: str,
) -> None:
    asyncio.run(_generate_reconciliation(tenant_id, run_id))


async def _generate_reconciliation(tenant_id: str, run_id: str) -> None:
    from sqlalchemy import and_, select
    from app.db.models.reconciliation import ReconciliationFlag, ReconciliationRun
    from app.db.repositories.reconciliation_repo import ReconciliationRepository
    from app.services.ai.insight_service import AIInsightService, InsightContextBuilder
    from app.db.repositories.ai_insight_repo import AIInsightRepository

    t_id = uuid.UUID(tenant_id)
    r_id = uuid.UUID(run_id)

    async with get_db_context() as db:
        recon_repo = ReconciliationRepository(db)
        run = await recon_repo.get_run(t_id, r_id)
        flags, _ = await recon_repo.list_flags(t_id, run_id=r_id, limit=200)

        svc = AIInsightService()
        repo = AIInsightRepository(db)

        ctx = InsightContextBuilder.reconciliation_summary(flags, run)
        result = svc.generate(
            "reconciliation_summary",
            ctx,
            str(run.period_start.date()) if hasattr(run.period_start, "date") else str(run.period_start),
            str(run.period_end.date()) if hasattr(run.period_end, "date") else str(run.period_end),
        )
        await repo.create(t_id, result, reconciliation_run_id=r_id)
        await db.commit()

    logger.info("reconciliation_insights_generated", tenant_id=tenant_id, run_id=run_id)


@celery_app.task(name="ai.generate_insights_on_demand", bind=True, max_retries=2, default_retry_delay=60)
def generate_insights_on_demand(
    self,
    tenant_id: str,
    insight_type: str,
    period_start: str,
    period_end: str,
    location_id: str | None = None,
) -> None:
    asyncio.run(_generate_on_demand(tenant_id, insight_type, period_start, period_end, location_id))


async def _generate_on_demand(
    tenant_id: str,
    insight_type: str,
    period_start: str,
    period_end: str,
    location_id: str | None,
) -> None:
    from datetime import datetime, timezone
    from app.services.pnl.calculator import PnLCalculator
    from app.services.ai.insight_service import AIInsightService, InsightContextBuilder
    from app.db.repositories.ai_insight_repo import AIInsightRepository

    t_id = uuid.UUID(tenant_id)
    loc_id = uuid.UUID(location_id) if location_id else None
    start_dt = datetime.fromisoformat(period_start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(period_end).replace(tzinfo=timezone.utc)

    async with get_db_context() as db:
        calculator = PnLCalculator(db)
        report = await calculator.compute(t_id, start_dt, end_dt, loc_id)

        if insight_type in ("pnl_summary",):
            ctx = InsightContextBuilder.pnl_summary(report)
        elif insight_type == "category_analysis":
            ctx = InsightContextBuilder.category_analysis(report)
        else:
            ctx = InsightContextBuilder.pnl_summary(report)

        svc = AIInsightService()
        repo = AIInsightRepository(db)
        result = svc.generate(insight_type, ctx, period_start, period_end)
        await repo.create(t_id, result, period_start, period_end, loc_id)
        await db.commit()

    logger.info("on_demand_insight_generated", tenant_id=tenant_id, insight_type=insight_type)
