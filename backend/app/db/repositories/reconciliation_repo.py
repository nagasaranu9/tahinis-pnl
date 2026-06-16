import uuid
from datetime import UTC, datetime
from decimal import Decimal

import structlog
from sqlalchemy import and_, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.reconciliation import ReconciliationFlag, ReconciliationRun

logger = structlog.get_logger(__name__)


class ReconciliationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------ runs

    async def create_run(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        triggered_by: uuid.UUID,
        location_id: uuid.UUID | None = None,
    ) -> ReconciliationRun:
        run = ReconciliationRun(
            tenant_id=tenant_id,
            location_id=location_id,
            period_start=period_start,
            period_end=period_end,
            triggered_by=triggered_by,
            status="pending",
        )
        self._db.add(run)
        await self._db.flush()
        return run

    async def get_run(self, tenant_id: uuid.UUID, run_id: uuid.UUID) -> ReconciliationRun:
        row = await self._db.execute(
            select(ReconciliationRun).where(
                and_(ReconciliationRun.tenant_id == tenant_id, ReconciliationRun.id == run_id)
            )
        )
        run = row.scalar_one_or_none()
        if run is None:
            raise NotFoundError(f"ReconciliationRun {run_id} not found")
        return run

    async def list_runs(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ReconciliationRun], int]:
        conditions = [ReconciliationRun.tenant_id == tenant_id]
        if location_id:
            # location_id is NULL on tenant-wide runs (e.g. the scheduled daily job,
            # which doesn't scope to a single location) — those still apply to every
            # location the tenant has, so don't filter them out of a location's view.
            conditions.append(
                or_(ReconciliationRun.location_id == location_id, ReconciliationRun.location_id.is_(None))
            )

        total = (await self._db.execute(
            select(func.count()).select_from(ReconciliationRun).where(and_(*conditions))
        )).scalar_one()

        rows = (await self._db.execute(
            select(ReconciliationRun)
            .where(and_(*conditions))
            .order_by(ReconciliationRun.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )).scalars().all()
        return list(rows), total

    async def start_run(self, run_id: uuid.UUID) -> None:
        run = await self._db.get(ReconciliationRun, run_id)
        if run:
            run.status = "running"
            run.started_at = datetime.now(UTC)
            await self._db.flush()

    async def complete_run(
        self,
        run_id: uuid.UUID,
        documents_checked: int,
        expenses_checked: int,
        toast_orders_checked: int,
        flags_raised: int,
        total_sales_amount: Decimal | None,
        total_expense_amount: Decimal | None,
    ) -> None:
        run = await self._db.get(ReconciliationRun, run_id)
        if run:
            run.status = "complete"
            run.completed_at = datetime.now(UTC)
            run.documents_checked = documents_checked
            run.expenses_checked = expenses_checked
            run.toast_orders_checked = toast_orders_checked
            run.flags_raised = flags_raised
            run.total_sales_amount = total_sales_amount
            run.total_expense_amount = total_expense_amount
            if total_sales_amount is not None and total_expense_amount is not None:
                run.net_variance = total_sales_amount - total_expense_amount
            await self._db.flush()

    async def fail_run(self, run_id: uuid.UUID, error_message: str) -> None:
        run = await self._db.get(ReconciliationRun, run_id)
        if run:
            run.status = "failed"
            run.completed_at = datetime.now(UTC)
            run.error_message = error_message
            await self._db.flush()

    # ----------------------------------------------------------------- flags

    async def create_flag(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        flag_type: str,
        severity: str,
        message: str,
        document_id: uuid.UUID | None = None,
        expense_id: uuid.UUID | None = None,
        toast_order_id: uuid.UUID | None = None,
    ) -> ReconciliationFlag:
        flag = ReconciliationFlag(
            tenant_id=tenant_id,
            run_id=run_id,
            flag_type=flag_type,
            severity=severity,
            message=message,
            document_id=document_id,
            expense_id=expense_id,
            toast_order_id=toast_order_id,
        )
        self._db.add(flag)
        await self._db.flush()
        return flag

    async def list_flags(
        self,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID | None = None,
        flag_type: str | None = None,
        unresolved_only: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[ReconciliationFlag], int]:
        conditions = [ReconciliationFlag.tenant_id == tenant_id]
        if run_id:
            conditions.append(ReconciliationFlag.run_id == run_id)
        if flag_type:
            conditions.append(ReconciliationFlag.flag_type == flag_type)
        if unresolved_only:
            conditions.append(ReconciliationFlag.is_resolved.is_(False))

        total = (await self._db.execute(
            select(func.count()).select_from(ReconciliationFlag).where(and_(*conditions))
        )).scalar_one()

        rows = (await self._db.execute(
            select(ReconciliationFlag)
            .where(and_(*conditions))
            .order_by(ReconciliationFlag.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )).scalars().all()
        return list(rows), total

    async def resolve_flag(
        self,
        tenant_id: uuid.UUID,
        flag_id: uuid.UUID,
        resolved_by: uuid.UUID,
        resolution_note: str,
    ) -> ReconciliationFlag:
        row = await self._db.execute(
            select(ReconciliationFlag).where(
                and_(ReconciliationFlag.tenant_id == tenant_id, ReconciliationFlag.id == flag_id)
            )
        )
        flag = row.scalar_one_or_none()
        if flag is None:
            raise NotFoundError(f"Flag {flag_id} not found")
        flag.is_resolved = True
        flag.resolved_by = resolved_by
        flag.resolved_at = datetime.now(UTC)
        flag.resolution_note = resolution_note
        await self._db.flush()
        return flag
