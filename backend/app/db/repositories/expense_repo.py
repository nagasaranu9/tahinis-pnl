import uuid
from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy import Integer, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
        tax_amount: Decimal | None = None,
    ) -> Expense:
        expense = Expense(
            tenant_id=tenant_id,
            document_id=document_id,
            location_id=location_id,
            vendor_name=vendor_name,
            amount=amount,
            tax_amount=tax_amount,
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

    async def bank_line_exists(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        vendor_name: str,
        amount: Decimal,
        expense_date: datetime,
    ) -> bool:
        """Precise dedup for bank-statement lines: same vendor AND amount AND date.

        A bank statement legitimately repeats a vendor many times (ALEX FOOD daily,
        PUSHOPERATIONS weekly) with different amounts — deduping on vendor alone
        collapses them to one row and destroys real cost. Only an identical
        vendor+amount+date triple is a genuine duplicate."""
        result = await self._db.execute(
            select(Expense.id).where(
                and_(
                    Expense.tenant_id == tenant_id,
                    Expense.document_id == document_id,
                    Expense.vendor_name == vendor_name,
                    Expense.amount == amount,
                    Expense.expense_date == expense_date,
                )
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def prior_user_override(
        self,
        tenant_id: uuid.UUID,
        vendor_name: str,
        amount: Decimal,
        expense_date: datetime,
        exclude_document_id: uuid.UUID | None = None,
    ) -> str | None:
        """Category a user manually set on this same charge in an earlier import.

        Keyed on the charge identity (vendor+amount+date), not the document, so a
        re-uploaded statement inherits the tenant's hand-categorization instead of
        reverting to the keyword/AI guess. Returns the category string, or None if
        the charge was never manually overridden."""
        conditions = [
            Expense.tenant_id == tenant_id,
            Expense.vendor_name == vendor_name,
            Expense.amount == amount,
            Expense.expense_date == expense_date,
            Expense.user_overridden.is_(True),
            Expense.category.is_not(None),
        ]
        if exclude_document_id is not None:
            conditions.append(Expense.document_id != exclude_document_id)
        result = await self._db.execute(
            select(Expense.category).where(and_(*conditions))
            .order_by(Expense.updated_at.desc()).limit(1)
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
        missing_tax_only: bool = False,
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
            # Match PnLCalculator: a location's view includes NULL-location rows
            # (bank statements uploaded without a location). Otherwise the Expenses
            # tab shows 0 while the P&L counts dozens — exactly the ghost mismatch.
            from sqlalchemy import or_ as _or
            conditions.append(
                _or(Expense.location_id == location_id, Expense.location_id.is_(None))
            )
        if category:
            conditions.append(Expense.category == category)
        if vendor_name:
            conditions.append(Expense.vendor_name.ilike(f"%{vendor_name}%"))
        if uncategorized_only:
            conditions.append(Expense.category.is_(None))
        if missing_tax_only:
            # Amount present but no HST captured — potential un-claimed ITC to chase
            # down against the source invoice.
            conditions.append(Expense.amount.isnot(None))
            conditions.append(Expense.tax_amount.is_(None))

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

    async def delete_in_range(
        self,
        tenant_id: uuid.UUID,
        start: datetime,
        end: datetime,
        location_id: uuid.UUID | None = None,
        include_overridden: bool = False,
    ) -> int:
        """Delete expenses whose expense_date falls in [start, end] for a tenant.

        Used to reset a corrupted reporting period to a clean slate before
        re-uploading/reprocessing the source statements (e.g. duplicated/phantom
        payroll rows from an earlier ingestion). By default user-overridden rows
        are preserved — those are manual decisions, not extraction guesses."""
        from sqlalchemy import delete as sa_delete, or_ as _or

        conds = [
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        ]
        if location_id is not None:
            # Mirror PnLCalculator._load_expenses: a location's P&L includes both
            # its own expenses AND tenant-wide rows with NULL location (e.g. bank
            # statements uploaded without a location). The purge MUST match that
            # same set or those NULL-location rows stay invisible to the Expenses
            # list (which filters strictly by location) yet keep inflating the P&L.
            conds.append(_or(Expense.location_id == location_id, Expense.location_id.is_(None)))
        if not include_overridden:
            conds.append(Expense.user_overridden == False)  # noqa: E712

        result = await self._db.execute(sa_delete(Expense).where(and_(*conds)))
        await self._db.flush()
        return result.rowcount or 0

    async def delete_by_document(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID, include_overridden: bool = False
    ) -> int:
        """Delete all expenses sourced from a document. Used before reprocessing so
        re-extraction starts clean (no stale/miscategorized rows from a prior run,
        and dedup-by-vendor doesn't block recreating corrected rows).

        include_overridden=False (default, reprocess) preserves user-overridden
        categorizations. include_overridden=True (explicit document delete) removes
        every derived row so deleting a document doesn't orphan its expenses into
        the P&L."""
        from sqlalchemy import and_, delete as sa_delete

        conds = [
            Expense.tenant_id == tenant_id,
            Expense.document_id == document_id,
        ]
        if not include_overridden:
            conds.append(Expense.user_overridden == False)  # noqa: E712
        result = await self._db.execute(sa_delete(Expense).where(and_(*conds)))
        await self._db.flush()
        return result.rowcount or 0

    async def delete_by_document_ids(
        self, tenant_id: uuid.UUID, document_ids: list[uuid.UUID]
    ) -> int:
        """Delete every expense derived from any of the given documents (all rows,
        including overridden). Used by bulk document delete."""
        from sqlalchemy import and_, delete as sa_delete

        if not document_ids:
            return 0
        result = await self._db.execute(
            sa_delete(Expense).where(
                and_(
                    Expense.tenant_id == tenant_id,
                    Expense.document_id.in_(document_ids),
                )
            )
        )
        await self._db.flush()
        return result.rowcount or 0

    async def hst_by_month(
        self,
        tenant_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
        location_id: uuid.UUID | None = None,
    ) -> list[tuple[int, int, Decimal, Decimal, int, int]]:
        """Sum recoverable HST/GST (Input Tax Credits) per calendar month.

        Returns rows of (year, month, tax_total, expense_total, doc_count,
        docs_missing_tax) for expenses whose expense_date is in [start, end].
        docs_missing_tax counts expenses with an amount but no tax captured —
        those are potential un-claimed ITCs worth a manual look."""
        from sqlalchemy import case, extract, or_ as _or

        yr = cast(extract("year", Expense.expense_date), Integer)
        mo = cast(extract("month", Expense.expense_date), Integer)
        missing = case(
            (and_(Expense.tax_amount.is_(None), Expense.amount.isnot(None)), 1),
            else_=0,
        )
        conds = [
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= start,
            Expense.expense_date <= end,
        ]
        if location_id is not None:
            conds.append(_or(Expense.location_id == location_id, Expense.location_id.is_(None)))

        rows = (
            await self._db.execute(
                select(
                    yr.label("yr"),
                    mo.label("mo"),
                    func.coalesce(func.sum(Expense.tax_amount), 0),
                    func.coalesce(func.sum(Expense.amount), 0),
                    func.count(Expense.id),
                    func.coalesce(func.sum(missing), 0),
                )
                .where(and_(*conds))
                .group_by("yr", "mo")
                .order_by("yr", "mo")
            )
        ).all()
        return [
            (int(r[0]), int(r[1]), Decimal(r[2]), Decimal(r[3]), int(r[4]), int(r[5]))
            for r in rows
        ]

    async def propagate_hst_to_bank_expenses(
        self,
        tenant_id: uuid.UUID,
        *,
        location_id: uuid.UUID | None = None,
        amount_tol: Decimal = Decimal("0.01"),
        date_window_days: int = 35,
    ) -> int:
        """Fill HST on bank-statement expenses from a matching invoice/receipt.

        A bank debit doesn't itemize HST, but the invoice behind it does. When a
        bank-statement expense (tax_amount NULL) equals an invoice/receipt total
        (within amount_tol) dated within date_window_days and that document has a
        captured tax_amount, copy the HST onto the bank expense so the ITC is
        recovered. Idempotent — only touches NULL-tax bank rows."""
        from datetime import timedelta

        bank_doc = aliased(Document)
        # Bank-statement expenses still missing HST.
        rows = (
            await self._db.execute(
                select(Expense.id, Expense.amount, Expense.expense_date, Expense.location_id)
                .join(bank_doc, bank_doc.id == Expense.document_id)
                .where(
                    Expense.tenant_id == tenant_id,
                    Expense.tax_amount.is_(None),
                    Expense.amount.isnot(None),
                    bank_doc.document_type == "bank_statement",
                    *( [Expense.location_id == location_id] if location_id is not None else [] ),
                )
            )
        ).all()

        updated = 0
        for exp_id, amount, exp_date, _loc in rows:
            lo = exp_date - timedelta(days=date_window_days)
            hi = exp_date + timedelta(days=date_window_days)
            doc = (
                await self._db.execute(
                    select(Document.tax_amount)
                    .where(
                        Document.tenant_id == tenant_id,
                        Document.document_type.in_(["invoice", "receipt"]),
                        Document.tax_amount.isnot(None),
                        Document.tax_amount > 0,
                        Document.total_amount.isnot(None),
                        func.abs(Document.total_amount - amount) <= amount_tol,
                        Document.document_date >= lo,
                        Document.document_date <= hi,
                    )
                    .order_by(func.abs(Document.total_amount - amount))
                    .limit(1)
                )
            ).first()
            if doc is None:
                continue
            exp = await self._db.get(Expense, exp_id)
            if exp is not None and exp.tax_amount is None:
                exp.tax_amount = doc[0]
                updated += 1
        if updated:
            await self._db.flush()
        return updated

    async def hst_collected_by_month(
        self,
        tenant_id: uuid.UUID,
        *,
        start: datetime,
        end: datetime,
        location_id: uuid.UUID | None = None,
    ) -> dict[tuple[int, int], Decimal]:
        """Sum HST/GST collected on Toast sales per calendar month, keyed by
        (year, month). This is the tax you owe CRA before subtracting ITCs.

        Toast business_date is a 'YYYYMMDD' string (4am→3:59am day boundary), so
        year/month come from string slices, not a date extract."""
        from app.db.models.toast import ToastOrder

        yr = cast(func.substr(ToastOrder.business_date, 1, 4), Integer)
        mo = cast(func.substr(ToastOrder.business_date, 5, 2), Integer)
        conds = [
            ToastOrder.tenant_id == tenant_id,
            ToastOrder.business_date >= start.strftime("%Y%m%d"),
            ToastOrder.business_date <= end.strftime("%Y%m%d"),
        ]
        if location_id is not None:
            conds.append(ToastOrder.location_id == location_id)

        rows = (
            await self._db.execute(
                select(yr.label("yr"), mo.label("mo"), func.coalesce(func.sum(ToastOrder.tax_amount), 0))
                .where(and_(*conds))
                .group_by("yr", "mo")
            )
        ).all()
        return {(int(r[0]), int(r[1])): Decimal(r[2]) for r in rows}
