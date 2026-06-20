import uuid
from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.expense import Expense

logger = structlog.get_logger(__name__)


class ExpenseRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_from_document(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID | None,
        vendor_name: str | None,
        amount: Decimal | None,
        currency_code: str,
        location_id: uuid.UUID | None,
        created_by: uuid.UUID | None,
        expense_date: datetime,
        category: str | None = None,
        user_overridden: bool = False,
    ) -> Expense:
        expense = Expense(
            tenant_id=tenant_id,
            document_id=document_id,
            location_id=location_id,
            vendor_name=vendor_name,
            amount=amount,
            currency_code=currency_code,
            created_by=created_by,
            expense_date=expense_date,
            category=category,
            user_overridden=user_overridden,
        )
        self._db.add(expense)
        await self._db.flush()
        return expense

    async def get(self, tenant_id: uuid.UUID, expense_id: uuid.UUID) -> Expense:
        result = await self._db.execute(
            select(Expense).where(
                and_(Expense.tenant_id == tenant_id, Expense.id == expense_id)
            )
        )
        expense = result.scalar_one_or_none()
        if expense is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError(f"Expense {expense_id} not found")
        return expense

    async def get_by_document(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Expense | None:
        result = await self._db.execute(
            select(Expense).where(
                and_(Expense.tenant_id == tenant_id, Expense.document_id == document_id)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_document_and_vendor(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, vendor_name: str
    ) -> Expense | None:
        result = await self._db.execute(
            select(Expense).where(
                and_(
                    Expense.tenant_id == tenant_id,
                    Expense.document_id == document_id,
                    Expense.vendor_name == vendor_name,
                )
            )
        )
        return result.scalar_one_or_none()

    async def payroll_duplicate_exists(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None,
        expense_date: datetime,
        amount: Decimal,
        vendor_name: str | None,
    ) -> bool:
        """True if an identical Payroll expense already exists for this period.

        Re-importing the same PushOps export must not double-count labor, so we
        dedup on the natural key (tenant, location, date, amount, vendor).
        """
        conditions = [
            Expense.tenant_id == tenant_id,
            Expense.category == "Payroll",
            Expense.expense_date == expense_date,
            Expense.amount == amount,
        ]
        if location_id is None:
            conditions.append(Expense.location_id.is_(None))
        else:
            conditions.append(Expense.location_id == location_id)
        if vendor_name is None:
            conditions.append(Expense.vendor_name.is_(None))
        else:
            conditions.append(Expense.vendor_name == vendor_name)

        result = await self._db.execute(
            select(Expense.id).where(and_(*conditions)).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def list_expenses(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None = None,
        category: str | None = None,
        vendor_name: str | None = None,
        uncategorized_only: bool = False,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[Expense], int]:
        conditions = [
            Expense.tenant_id == tenant_id,
            # exclude expenses whose source document was flagged as a duplicate
            ~(
                select(Document.id)
                .where(
                    Document.id == Expense.document_id,
                    Document.is_duplicate.is_(True),
                )
                .correlate(Expense)
                .exists()
            ),
        ]
        if location_id:
            conditions.append(Expense.location_id == location_id)
        if category:
            conditions.append(Expense.category == category)
        if vendor_name:
            conditions.append(Expense.vendor_name.ilike(f"%{vendor_name}%"))
        if uncategorized_only:
            conditions.append(Expense.category.is_(None))

        count_q = select(func.count()).select_from(Expense).where(and_(*conditions))
        total = (await self._db.execute(count_q)).scalar_one()

        offset = (page - 1) * limit
        rows_q = (
            select(Expense)
            .where(and_(*conditions))
            .order_by(Expense.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._db.execute(rows_q)).scalars().all()
        return list(rows), total

    async def apply_ai_categorization(
        self,
        expense_id: uuid.UUID,
        ai_suggested_category: str,
        ai_confidence_score: Decimal,
        ai_explanation: str,
    ) -> None:
        expense = await self._db.get(Expense, expense_id)
        if expense is None:
            return
        expense.ai_suggested_category = ai_suggested_category
        expense.ai_confidence_score = ai_confidence_score
        expense.ai_explanation = ai_explanation
        expense.is_ai_categorized = True
        # Auto-apply the suggestion whenever the user hasn't manually overridden.
        # A suggested category (even low-confidence) is strictly better than
        # leaving the expense Uncategorized in the P&L — the user can still
        # override, and low confidence is surfaced in the UI. Only a real user
        # override (user_overridden=True) is protected from being clobbered.
        if not expense.user_overridden:
            expense.category = ai_suggested_category
        await self._db.flush()

    async def override_category(
        self, tenant_id: uuid.UUID, expense_id: uuid.UUID, category: str
    ) -> Expense:
        expense = await self.get(tenant_id, expense_id)
        expense.category = category
        expense.user_overridden = True
        await self._db.flush()
        return expense

    async def update_from_ocr(
        self,
        tenant_id: uuid.UUID,
        expense_id: uuid.UUID,
        amount: "Decimal | None",
        vendor_name: str | None,
        currency_code: str | None,
    ) -> None:
        expense = await self.get(tenant_id, expense_id)
        if amount is not None:
            expense.amount = amount
        if vendor_name:
            expense.vendor_name = vendor_name
        if currency_code:
            expense.currency_code = currency_code
        await self._db.flush()

    async def delete(self, tenant_id: uuid.UUID, expense_id: uuid.UUID) -> None:
        expense = await self.get(tenant_id, expense_id)
        await self._db.delete(expense)
        await self._db.flush()

    async def delete_by_document(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> int:
        """Delete all expenses sourced from a document. Used before reprocessing so
        re-extraction starts clean (no stale/miscategorized rows from a prior run,
        and dedup-by-vendor doesn't block recreating corrected rows). Preserves
        user-overridden categorizations — those are manual decisions, not guesses."""
        from sqlalchemy import and_, delete as sa_delete

        result = await self._db.execute(
            sa_delete(Expense).where(
                and_(
                    Expense.tenant_id == tenant_id,
                    Expense.document_id == document_id,
                    Expense.user_overridden == False,  # noqa: E712
                )
            )
        )
        await self._db.flush()
        return result.rowcount or 0
