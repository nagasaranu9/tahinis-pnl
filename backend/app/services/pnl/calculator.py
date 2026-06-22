"""P&L calculator service.

Computes P&L line items from Toast sales + categorized expenses.
All arithmetic uses Decimal. Never modifies source records.

P&L structure:
  Gross Revenue   = sum(net_amount + discount_amount) for non-void orders
  Total Discounts = sum(discount_amount) for non-void orders
  Net Revenue     = Gross Revenue - Total Discounts
  COGS            = Food Cost + Beverage Cost + Packaging expenses
  Gross Profit    = Net Revenue - COGS
  Labor Cost      = Payroll expenses
  Prime Cost      = COGS + Labor Cost
  Opex            = all other expenses (not COGS / Payroll)
  EBITDA          = Net Revenue - COGS - Labor Cost - Opex
  Net Profit      = EBITDA  (simplified; no D/A or interest data)
"""
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.location import Location
from app.db.models.toast import ToastOrder
from app.schemas.pnl import ExpenseCategoryBreakdown, ExpenseLineItem, PnLLineItems, PnLReportResponse

logger = structlog.get_logger(__name__)

# Expense categories that map to COGS
_COGS_CATEGORIES = {"Food Cost", "Beverage Cost", "Packaging"}
# Expense categories that map to Labor
_LABOR_CATEGORIES = {"Payroll"}


def _pct(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PnLCalculator:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def compute(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None = None,
        currency_code: str = "CAD",
    ) -> PnLReportResponse:
        orders = await self._load_orders(tenant_id, period_start, period_end, location_id)
        expenses = await self._load_expenses(tenant_id, period_start, period_end, location_id)
        pipeboard_expenses = await self._load_pipeboard_metrics(tenant_id, period_start, period_end, location_id)
        location = await self._load_location(tenant_id, location_id) if location_id else None
        bank_statement_verified = await self._has_bank_statement(
            tenant_id, period_start, period_end, location_id
        )

        # Merge Pipeboard metrics into expenses
        all_expenses = expenses + pipeboard_expenses

        # ------------------------------------------------------------------
        # Revenue
        # ------------------------------------------------------------------
        gross_revenue = Decimal("0")
        total_discounts = Decimal("0")
        for order in orders:
            if order.is_void:
                continue
            if order.net_amount is not None:
                gross_revenue += order.net_amount
            if order.discount_amount is not None:
                total_discounts += order.discount_amount
                gross_revenue += order.discount_amount  # add back discounts to get pre-discount total

        net_revenue = gross_revenue - total_discounts

        # ------------------------------------------------------------------
        # Expenses by category
        # ------------------------------------------------------------------
        category_totals: dict[str, list[Expense]] = defaultdict(list)
        for exp in all_expenses:
            cat = exp.category or "Uncategorized"
            category_totals[cat].append(exp)

        def _sum_cat(cats: set[str]) -> Decimal:
            return sum(
                (exp.amount for c in cats for exp in category_totals.get(c, []) if exp.amount),
                Decimal("0"),
            )

        # Prorate rent from location settings into Rent category — but only when
        # there's no real Rent expense already for the period (e.g. pulled from an
        # actual bank/Amex statement line). Real data beats an estimate; without
        # this check a real Rent expense and the settings-based proration would
        # both land in the Rent category and double the figure.
        if location and location.rent_monthly_incl_hst and not category_totals.get("Rent"):
            period_days = (period_end - period_start).days + 1
            prorated_rent = (
                location.rent_monthly_incl_hst
                * Decimal(period_days)
                / Decimal("30.4375")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            # Inject synthetic rent expense so it flows into opex + breakdown
            _synthetic_rent = type("_R", (), {"amount": prorated_rent, "category": "Rent"})()
            category_totals["Rent"].append(_synthetic_rent)

        cogs = _sum_cat(_COGS_CATEGORIES)
        labor_cost = _sum_cat(_LABOR_CATEGORIES)
        opex_cats = set(category_totals.keys()) - _COGS_CATEGORIES - _LABOR_CATEGORIES
        operating_expenses = _sum_cat(opex_cats)

        gross_profit = net_revenue - cogs
        prime_cost = cogs + labor_cost
        ebitda = net_revenue - cogs - labor_cost - operating_expenses
        net_profit = ebitda  # simplified

        # ------------------------------------------------------------------
        # Percentage breakdowns
        # ------------------------------------------------------------------
        nr = net_revenue if net_revenue != 0 else None
        line_items = PnLLineItems(
            gross_revenue=gross_revenue or None,
            total_discounts=total_discounts or None,
            net_revenue=net_revenue or None,
            cogs=cogs or None,
            gross_profit=gross_profit if gross_profit != 0 else None,
            labor_cost=labor_cost or None,
            prime_cost=prime_cost or None,
            operating_expenses=operating_expenses or None,
            ebitda=ebitda if ebitda != 0 else None,
            net_profit=net_profit if net_profit != 0 else None,
            cogs_pct=_pct(cogs, nr),
            labor_pct=_pct(labor_cost, nr),
            prime_cost_pct=_pct(prime_cost, nr),
            ebitda_pct=_pct(ebitda, nr),
            net_profit_pct=_pct(net_profit, nr),
        )

        # ------------------------------------------------------------------
        # Expense breakdown
        # ------------------------------------------------------------------
        breakdown: list[ExpenseCategoryBreakdown] = []
        for cat, exps in sorted(category_totals.items()):
            total = sum((e.amount for e in exps if e.amount), Decimal("0"))
            if total:
                breakdown.append(
                    ExpenseCategoryBreakdown(
                        category=cat,
                        total=total,
                        expense_count=len(exps),
                        expenses=[
                            ExpenseLineItem(vendor_name=getattr(e, "vendor_name", None), amount=e.amount)
                            for e in exps
                            if e.amount
                        ],
                    )
                )

        logger.info(
            "pnl_computed",
            tenant_id=str(tenant_id),
            net_revenue=str(net_revenue),
            orders=len(orders),
            expenses=len(all_expenses),
            pipeboard_expenses=len(pipeboard_expenses),
        )

        return PnLReportResponse(
            tenant_id=tenant_id,
            location_id=location_id,
            period_start=period_start.strftime("%Y-%m-%d"),
            period_end=period_end.strftime("%Y-%m-%d"),
            currency_code=currency_code,
            line_items=line_items,
            expense_breakdown=breakdown,
            order_count=sum(1 for o in orders if not o.is_void),
            expense_count=len(all_expenses),
            bank_statement_verified=bank_statement_verified,
            bank_statement_warning=(
                None
                if bank_statement_verified
                else "No bank statement on file for this period — figures are unreconciled and may not reflect a complete P&L. Upload a bank statement covering this date range."
            ),
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def _load_orders(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list[ToastOrder]:
        # Use Toast's native business_date (YYYYMMDD string, 4am→3:59am day boundary)
        start_str = period_start.strftime("%Y%m%d")
        end_str = period_end.strftime("%Y%m%d")
        conds = [
            ToastOrder.tenant_id == tenant_id,
            ToastOrder.business_date >= start_str,
            ToastOrder.business_date <= end_str,
        ]
        if location_id:
            conds.append(ToastOrder.location_id == location_id)
        rows = await self._db.execute(select(ToastOrder).where(and_(*conds)))
        return list(rows.scalars().all())

    async def _load_expenses(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list[Expense]:
        conds = [
            Expense.tenant_id == tenant_id,
            Expense.expense_date >= period_start,
            Expense.expense_date <= period_end,
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
            from sqlalchemy import or_ as _or
            conds.append(
                _or(Expense.location_id == location_id, Expense.location_id.is_(None))
            )
        # Pull the source document_type alongside each expense so we can tell a
        # bank-statement line from an uploaded invoice/receipt (needed for dedup).
        rows = await self._db.execute(
            select(Expense, Document.document_type)
            .outerjoin(Document, Document.id == Expense.document_id)
            .where(and_(*conds))
        )
        expenses: list[Expense] = []
        for exp, doc_type in rows.all():
            exp._doc_type = doc_type  # type: ignore[attr-defined]
            expenses.append(exp)
        return self._dedup_bank_vs_invoice(expenses)

    @staticmethod
    def _norm_vendor(name: str | None) -> str | None:
        if not name:
            return None
        return " ".join(name.lower().split())

    def _dedup_bank_vs_invoice(self, expenses: list[Expense]) -> list[Expense]:
        """Bank statement wins. When a vendor has a bank-statement expense in the
        period, the actual cash already captures that spend, so drop that vendor's
        uploaded-invoice/receipt expenses to avoid double-counting (e.g. Alex Food
        invoices + the bank payment to Alex)."""
        bank_vendors = {
            self._norm_vendor(e.vendor_name)
            for e in expenses
            if getattr(e, "_doc_type", None) == "bank_statement" and e.vendor_name
        }
        bank_vendors.discard(None)
        if not bank_vendors:
            return expenses

        kept: list[Expense] = []
        for e in expenses:
            if getattr(e, "_doc_type", None) == "bank_statement":
                kept.append(e)
                continue
            v = self._norm_vendor(e.vendor_name)
            if v and any(bv in v or v in bv for bv in bank_vendors):
                logger.info(
                    "pnl_dedup_dropped_invoice",
                    vendor=e.vendor_name,
                    amount=str(e.amount),
                    reason="bank_statement_covers_vendor",
                )
                continue
            kept.append(e)
        return kept

    async def _load_location(
        self,
        tenant_id: uuid.UUID,
        location_id: uuid.UUID,
    ) -> Location | None:
        rows = await self._db.execute(
            select(Location).where(
                Location.id == location_id,
                Location.tenant_id == tenant_id,
            )
        )
        return rows.scalar_one_or_none()

    async def _load_pipeboard_metrics(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> list:
        """Load Pipeboard metrics as synthetic expenses with category mapping applied."""
        from app.db.models.external_platform import PipeboardDailyMetric, PipeboardCampaign
        from app.db.repositories.pipeboard_repo import PipeboardRepository

        period_start_str = period_start.strftime("%Y-%m-%d")
        period_end_str = period_end.strftime("%Y-%m-%d")

        conds = [
            PipeboardDailyMetric.tenant_id == tenant_id,
            PipeboardDailyMetric.metric_date >= period_start_str,
            PipeboardDailyMetric.metric_date <= period_end_str,
        ]

        rows = await self._db.execute(select(PipeboardDailyMetric).where(and_(*conds)))
        metrics = list(rows.scalars().all())

        if not metrics:
            return []

        # Load campaigns for mapping
        campaign_map = {}
        camp_rows = await self._db.execute(
            select(PipeboardCampaign).where(PipeboardCampaign.tenant_id == tenant_id)
        )
        for camp in camp_rows.scalars().all():
            campaign_map[camp.id] = camp

        # Get category mappings
        repo = PipeboardRepository(self._db)

        # Convert metrics to synthetic expense objects
        synthetic_expenses = []
        platform_spend: dict[str, Decimal] = defaultdict(Decimal)

        for metric in metrics:
            campaign = campaign_map.get(metric.campaign_id)
            if not campaign:
                continue

            # Get category mapping for this campaign
            mapping = await repo.get_category_mapping(
                tenant_id=tenant_id,
                pipeboard_platform=campaign.pipeboard_platform,
                campaign_type=campaign.campaign_type,
            )

            category = mapping.expense_category if mapping else "Marketing"

            # Track spend by platform for platform breakdown
            platform_spend[campaign.pipeboard_platform] += metric.spend

            # Create synthetic expense-like object
            synthetic_exp = type("_PB", (), {
                "amount": metric.spend,
                "category": category,
                "vendor_name": f"{campaign.name} ({campaign.pipeboard_platform})",
            })()

            synthetic_expenses.append(synthetic_exp)

        return synthetic_expenses

    async def _has_bank_statement(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> bool:
        from sqlalchemy import or_
        base_conds = [
            Document.tenant_id == tenant_id,
            Document.document_type == "bank_statement",
            # Google Invoice Parser doesn't extract dates from bank statements so
            # document_date is often NULL. Fall back to created_at (upload date) so
            # the "No bank statement" warning doesn't appear for freshly uploaded statements.
            or_(
                and_(
                    Document.document_date.is_not(None),
                    Document.document_date >= period_start,
                    Document.document_date <= period_end,
                ),
                and_(
                    Document.document_date.is_(None),
                    Document.created_at >= period_start,
                    Document.created_at <= period_end,
                ),
            ),
        ]
        if location_id:
            # Match documents scoped to this location OR documents with no location
            # (bank statements are typically uploaded tenant-wide, not per-location).
            from sqlalchemy import or_ as sa_or
            base_conds.append(
                sa_or(Document.location_id == location_id, Document.location_id.is_(None))
            )
        result = await self._db.execute(select(Document.id).where(and_(*base_conds)).limit(1))
        return result.scalar_one_or_none() is not None
