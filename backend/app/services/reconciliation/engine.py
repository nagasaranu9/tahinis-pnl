"""Reconciliation engine.

Reconciles Toast sales, document expenses, and flags anomalies.
All financial calculations use Decimal. No AI writes to source records.
"""
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from statistics import mean, stdev

import structlog
from sqlalchemy import and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.toast import ToastOrder
from app.db.repositories.reconciliation_repo import ReconciliationRepository

logger = structlog.get_logger(__name__)

# Anomaly threshold: flag if amount deviates by more than this many stddevs from vendor mean.
# Requires at least MIN_VENDOR_SAMPLES samples.
ANOMALY_STDDEV_THRESHOLD = 3
MIN_VENDOR_SAMPLES = 5


class ReconciliationEngine:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ReconciliationRepository(db)

    async def run(
        self,
        run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> None:
        await self._repo.start_run(run_id)
        await self._db.commit()

        try:
            result = await self._execute(run_id, tenant_id, period_start, period_end, location_id)
            await self._repo.complete_run(run_id, **result)
            await self._db.commit()
        except Exception as exc:
            await self._repo.fail_run(run_id, str(exc))
            await self._db.commit()
            logger.error("reconciliation_failed", run_id=str(run_id), error=str(exc))
            raise

    async def _execute(
        self,
        run_id: uuid.UUID,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> dict:
        flags_raised = 0

        # ---- Load data -------------------------------------------------------
        documents = await self._load_documents(tenant_id, period_start, period_end, location_id)
        expenses = await self._load_expenses(tenant_id, period_start, period_end, location_id)
        toast_orders = await self._load_toast_orders(tenant_id, period_start, period_end, location_id)

        # ---- Derived lookups -------------------------------------------------
        expense_by_doc: dict[uuid.UUID, list[Expense]] = defaultdict(list)
        for exp in expenses:
            if exp.document_id:
                expense_by_doc[exp.document_id].append(exp)

        # Vendor amount history for anomaly detection (all time, not just this period)
        vendor_amounts = await self._load_vendor_amount_history(tenant_id, location_id)

        # ---- Flag: duplicate_invoice -----------------------------------------
        for doc in documents:
            if doc.is_duplicate:
                await self._repo.create_flag(
                    tenant_id=tenant_id, run_id=run_id,
                    flag_type="duplicate_invoice", severity="high",
                    message=f"Document '{doc.original_filename}' is marked as duplicate (original: {doc.duplicate_of}).",
                    document_id=doc.id,
                )
                flags_raised += 1

        # ---- Flag: duplicate_expense (>1 expense per document) ---------------
        for doc_id, exps in expense_by_doc.items():
            if len(exps) > 1:
                for exp in exps:
                    await self._repo.create_flag(
                        tenant_id=tenant_id, run_id=run_id,
                        flag_type="duplicate_expense", severity="critical",
                        message=f"Document {doc_id} has {len(exps)} expense records (IDs: {[str(e.id) for e in exps]}).",
                        document_id=doc_id, expense_id=exp.id,
                    )
                    flags_raised += 1

        # ---- Flag: uncategorized_expense -------------------------------------
        for exp in expenses:
            if exp.category is None:
                await self._repo.create_flag(
                    tenant_id=tenant_id, run_id=run_id,
                    flag_type="uncategorized_expense", severity="medium",
                    message=f"Expense {exp.id} (vendor: {exp.vendor_name}, amount: {exp.amount}) has no category.",
                    expense_id=exp.id,
                    document_id=exp.document_id,
                )
                flags_raised += 1

        # ---- Flag: suspicious_amount (z-score anomaly) -----------------------
        for exp in expenses:
            if exp.vendor_name and exp.amount is not None:
                amounts = vendor_amounts.get(exp.vendor_name, [])
                if len(amounts) >= MIN_VENDOR_SAMPLES:
                    avg = Decimal(str(mean(float(a) for a in amounts)))
                    sd = Decimal(str(stdev(float(a) for a in amounts)))
                    if sd > 0 and abs(exp.amount - avg) > ANOMALY_STDDEV_THRESHOLD * sd:
                        await self._repo.create_flag(
                            tenant_id=tenant_id, run_id=run_id,
                            flag_type="suspicious_amount", severity="high",
                            message=(
                                f"Expense {exp.id} amount {exp.amount} for vendor '{exp.vendor_name}' "
                                f"deviates {abs(exp.amount - avg):.2f} from mean {avg:.2f} "
                                f"(threshold: {ANOMALY_STDDEV_THRESHOLD}σ = {ANOMALY_STDDEV_THRESHOLD * sd:.2f})."
                            ),
                            expense_id=exp.id,
                            document_id=exp.document_id,
                        )
                        flags_raised += 1

        # ---- Flag: unmatched_sale (Toast day with no expense document) -------
        # Group Toast orders by business date; flag dates with sales but no expense
        toast_dates: dict[str, Decimal] = defaultdict(Decimal)
        for order in toast_orders:
            if order.business_date and not order.is_void and order.net_amount is not None:
                toast_dates[order.business_date] += order.net_amount

        # Group expenses by document_date
        expense_dates: set[str] = set()
        for exp in expenses:
            if exp.document_id:
                # Date comes from linked doc; approximate via expense.created_at date portion
                expense_dates.add(exp.created_at.strftime("%Y%m%d"))

        for business_date, sales_total in toast_dates.items():
            if sales_total > 0 and business_date not in expense_dates:
                await self._repo.create_flag(
                    tenant_id=tenant_id, run_id=run_id,
                    flag_type="unmatched_sale", severity="medium",
                    message=(
                        f"Toast sales of {sales_total} on {business_date} "
                        f"have no corresponding expense documents for that day."
                    ),
                )
                flags_raised += 1

        # ---- Aggregate totals ------------------------------------------------
        total_sales = sum(
            (o.net_amount for o in toast_orders if o.net_amount and not o.is_void),
            Decimal("0"),
        ) or None
        total_expenses = sum(
            (e.amount for e in expenses if e.amount),
            Decimal("0"),
        ) or None

        logger.info(
            "reconciliation_complete",
            run_id=str(run_id),
            documents=len(documents),
            expenses=len(expenses),
            toast_orders=len(toast_orders),
            flags=flags_raised,
        )

        return {
            "documents_checked": len(documents),
            "expenses_checked": len(expenses),
            "toast_orders_checked": len(toast_orders),
            "flags_raised": flags_raised,
            "total_sales_amount": total_sales,
            "total_expense_amount": total_expenses,
        }

    # ----------------------------------------------------------------- queries

    async def _load_documents(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list[Document]:
        conditions = [
            Document.tenant_id == tenant_id,
            Document.created_at >= period_start,
            Document.created_at <= period_end,
        ]
        if location_id:
            conditions.append(Document.location_id == location_id)
        rows = await self._db.execute(select(Document).where(and_(*conditions)))
        return list(rows.scalars().all())

    async def _load_expenses(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list[Expense]:
        conditions = [
            Expense.tenant_id == tenant_id,
            Expense.created_at >= period_start,
            Expense.created_at <= period_end,
        ]
        if location_id:
            conditions.append(Expense.location_id == location_id)
        rows = await self._db.execute(select(Expense).where(and_(*conditions)))
        return list(rows.scalars().all())

    async def _load_toast_orders(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list[ToastOrder]:
        conditions = [
            ToastOrder.tenant_id == tenant_id,
            ToastOrder.closed_at >= period_start,
            ToastOrder.closed_at <= period_end,
        ]
        if location_id:
            conditions.append(ToastOrder.location_id == location_id)
        rows = await self._db.execute(select(ToastOrder).where(and_(*conditions)))
        return list(rows.scalars().all())

    async def _load_vendor_amount_history(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID | None,
    ) -> dict[str, list[Decimal]]:
        conditions = [
            Expense.tenant_id == tenant_id,
            Expense.vendor_name.isnot(None),
            Expense.amount.isnot(None),
        ]
        if location_id:
            conditions.append(Expense.location_id == location_id)
        rows = await self._db.execute(
            select(Expense.vendor_name, Expense.amount).where(and_(*conditions))
        )
        result: dict[str, list[Decimal]] = defaultdict(list)
        for vendor_name, amount in rows.all():
            result[vendor_name].append(amount)
        return result
