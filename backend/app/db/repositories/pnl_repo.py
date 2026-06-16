"""P&L snapshot repository."""
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.pnl import PnLSnapshot
from app.schemas.pnl import PnLReportResponse


class PnLRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert_snapshot(
        self,
        report: PnLReportResponse,
        period_label: str,
        created_by: uuid.UUID | None = None,
    ) -> PnLSnapshot:
        li = report.line_items
        stmt = (
            pg_insert(PnLSnapshot)
            .values(
                tenant_id=report.tenant_id,
                location_id=report.location_id,
                period_start=report.period_start,
                period_end=report.period_end,
                period_label=period_label,
                gross_revenue=li.gross_revenue,
                total_discounts=li.total_discounts,
                net_revenue=li.net_revenue,
                cogs=li.cogs,
                gross_profit=li.gross_profit,
                labor_cost=li.labor_cost,
                prime_cost=li.prime_cost,
                operating_expenses=li.operating_expenses,
                ebitda=li.ebitda,
                net_profit=li.net_profit,
                order_count=report.order_count,
                expense_count=report.expense_count,
                created_by=created_by,
            )
            .on_conflict_do_update(
                constraint="uq_pnl_snapshot",
                set_={
                    "gross_revenue": li.gross_revenue,
                    "total_discounts": li.total_discounts,
                    "net_revenue": li.net_revenue,
                    "cogs": li.cogs,
                    "gross_profit": li.gross_profit,
                    "labor_cost": li.labor_cost,
                    "prime_cost": li.prime_cost,
                    "operating_expenses": li.operating_expenses,
                    "ebitda": li.ebitda,
                    "net_profit": li.net_profit,
                    "order_count": report.order_count,
                    "expense_count": report.expense_count,
                },
            )
            .returning(PnLSnapshot)
        )
        result = await self._db.execute(stmt)
        snapshot = result.scalar_one()
        await self._db.flush()
        return snapshot

    async def list_snapshots(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 24,
    ) -> tuple[list[PnLSnapshot], int]:
        from sqlalchemy import func

        conds = [PnLSnapshot.tenant_id == tenant_id]
        if location_id:
            conds.append(PnLSnapshot.location_id == location_id)

        total_q = await self._db.execute(
            select(func.count()).select_from(PnLSnapshot).where(and_(*conds))
        )
        total = total_q.scalar_one()

        rows = await self._db.execute(
            select(PnLSnapshot)
            .where(and_(*conds))
            .order_by(PnLSnapshot.period_start.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows.scalars().all()), total
