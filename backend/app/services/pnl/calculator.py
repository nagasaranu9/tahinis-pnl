"""P&L calculator service.

Computes P&L line items from Toast sales + categorized expenses.
All arithmetic uses Decimal. Never modifies source records.

P&L structure:
  Gross Revenue   = sum(net_amount + discount_amount) for non-void orders
  Total Discounts = sum(discount_amount) for non-void orders
  Net Revenue     = Gross Revenue - Total Discounts
  COGS            = Food Cost + Beverage Cost + Packaging expenses
  Gross Profit    = Net Revenue - COGS
  Labor Cost      = PushOperations actual labour when the integration is active,
                    otherwise Payroll expenses (bank statement / payroll CSV)
  Prime Cost      = COGS + Labor Cost
  Opex            = all other expenses (not COGS / Payroll)
  EBITDA          = Net Revenue - COGS - Labor Cost - Opex
  Net Profit      = EBITDA  (simplified; no D/A or interest data)
"""
import re
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
# Expense categories that map to Labor.
#
# These are cash-out records (pre-authorized payroll debits off the bank
# statement, payroll CSV imports). They are only used for the Labor line when
# the PushOperations integration is inactive. When Push IS active, Push actuals
# are the Labor source and these expenses are excluded from the P&L entirely —
# counting both would double the Labor line, since they describe the same wages
# from two angles (accrued cost vs cash paid).
_LABOR_CATEGORIES = {"Payroll"}

# Categories where an uploaded invoice is the source of truth, not the bank
# debit that later clears it. _dedup_bank_vs_invoice's default ("bank wins")
# works for vendors whose bank description resembles their invoice name
# (e.g. "Alex Food"), but the franchisor's bank line reads
# "Pre-Authorized Payment, TAHINIS BUS/ENT" against an invoice vendor of
# "Tahinis Franchising Corp" — only one shared token ("tahinis"), below the
# 2-token match threshold, so the generic pass never catches it and both
# sides land in Royalties, doubling it. Matched on amount instead of vendor
# tokens; see _dedup_invoice_vs_bank_by_amount.
_INVOICE_WINS_CATEGORIES = {"Royalties"}

# Tolerance for matching an invoice amount to a bank debit as "the same
# charge" — same magnitude as the payroll-vs-bank check in the reconciliation
# engine (OCR rounding, minor fee differences).
_ROYALTY_MATCH_ABS = Decimal("1.00")
_ROYALTY_MATCH_PCT = Decimal("0.005")

# Vendor identity token that marks the franchisor. The franchisor (Tahinis
# Franchising Corp) bills the same weekly royalty/marketing/delivery charges
# through THREE overlapping document formats, all of which get ingested and
# expensed:
#   1. Atomic per-charge invoice  — "Invoice_21284_from_Tahinis…", one
#      invoice number, one week, one category. This is the truth.
#   2. Weekly/periodic statement  — "Statement_6772_from_Tahinis…", a rollup
#      that re-lists several invoice numbers (incl. ones already ingested
#      atomically) plus balance-forward/payment lines.
#   3. Monthly batch             — "1941 Tahinis Corp Invoices.pdf", a rollup
#      spanning many weeks with no single invoice number, often re-ingested
#      several times.
# Formats 2 and 3 re-state charges already captured by format 1, so counting
# them multiplies franchise Marketing/Royalties several-fold. _dedup_franchise
# _rollups keeps the atomic invoices and drops the statement/batch rollups.
_FRANCHISE_VENDOR_TOKEN = "franchising"


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
        # Pipeboard daily ad metrics are intentionally NOT merged into the P&L:
        # they report platform-side spend that can exceed what Google actually
        # bills (credits, thresholds, stale campaign data — June 2026 showed
        # $1,266 Pipeboard vs $624.79 billed). The Google billing invoice that
        # arrives by email is the source of truth for ad spend, entering the
        # P&L through the normal document→OCR→expense pipeline like any vendor
        # bill. Pipeboard data remains available for dashboards only.
        pipeboard_expenses: list = []
        location = await self._load_location(tenant_id, location_id) if location_id else None
        bank_statement_verified = await self._has_bank_statement(
            tenant_id, period_start, period_end, location_id
        )
        push_labor = await self._load_push_labor(
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

        # Labor precedence: PushOperations actuals replace Payroll expenses.
        #
        # Push reports accrued labour cost per business date; the Payroll
        # expenses are the bank's pre-authorized debits, which settle on a pay
        # date covering an earlier pay period. They describe the same wages, so
        # counting both would double the Labor line. Substituting (rather than
        # adding) keeps the Labor line and the expense breakdown telling the
        # same story. The real Payroll expenses stay in the database as the
        # month-end cross-check against Push — see the reconciliation engine.
        labor_source = "expenses"
        if push_labor is not None:
            labor_source = "pushoperations"
            category_totals["Payroll"] = [
                type("_P", (), {"amount": push_labor, "category": "Payroll", "vendor_name": "PushOperations (actual labour)"})()
            ]

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
            labor_source=labor_source,
            labor_cost=str(labor_cost),
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

    async def _load_push_labor(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
        location_id: uuid.UUID | None,
    ) -> Decimal | None:
        """
        Actual labour cost from PushOperations for the period.

        Returns None when the tenant has no active Push integration, which tells
        compute() to fall back to Payroll expenses. A tenant WITH an active
        integration but no rows in range returns Decimal("0") rather than None:
        that is a real zero (closed for the period), not a missing integration,
        and must not silently re-enable the expense fallback.
        """
        from app.services.labor.push_sync_service import get_active_config, labor_totals

        config = await get_active_config(self._db, tenant_id)
        if config is None:
            return None

        # Push keys rows on business_date (a real date), while the P&L period is
        # a timestamp range — take the calendar dates.
        cost, _hours = await labor_totals(
            self._db,
            tenant_id,
            period_start.date(),
            period_end.date(),
            location_id=location_id,
        )
        return cost

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
        # Pull the source document_type + filename alongside each expense so we
        # can tell a bank-statement line from an uploaded invoice/receipt, and
        # an atomic franchisor invoice from a statement/batch rollup (dedup).
        rows = await self._db.execute(
            select(Expense, Document.document_type, Document.original_filename)
            .outerjoin(Document, Document.id == Expense.document_id)
            .where(and_(*conds))
        )
        expenses: list[Expense] = []
        for exp, doc_type, filename in rows.all():
            exp._doc_type = doc_type  # type: ignore[attr-defined]
            exp._filename = filename  # type: ignore[attr-defined]
            expenses.append(exp)
        await self._annotate_franchise_roles(expenses)
        expenses = self._dedup_franchise_rollups(expenses)
        expenses = self._dedup_invoice_vs_bank_by_amount(expenses)
        return self._dedup_bank_vs_invoice(expenses)

    # Invoice-number token in a franchisor filename or OCR'd line-item
    # description: "Invoice_21284…", "Invoice #21357: Marketing", "INV-020768".
    _FRANCHISE_INV_RE = re.compile(r"(?:Invoice|INV)\s*[#_\-]?\s*0*(\d{4,})", re.IGNORECASE)

    @classmethod
    def _franchise_invoice_numbers(cls, filename: str | None, descriptions: list[str]) -> set[str]:
        nums: set[str] = set()
        for text in [filename or "", *descriptions]:
            for m in cls._FRANCHISE_INV_RE.finditer(text):
                nums.add(m.group(1).lstrip("0"))
        return nums

    async def _annotate_franchise_roles(self, expenses: list[Expense]) -> None:
        """Tag each franchisor expense with a role:
          - 'atomic'     — a single-invoice document, the source of truth.
          - 'rollup'     — a statement/batch re-listing charges already
                           captured atomically (uploaded invoice/receipt).
          - 'bank'       — the pre-authorized bank debit that settles those
                           invoices ("Pre-Authorized Payment, TAHINIS BUS/ENT").
        Non-franchisor expenses are left untagged.

        Atomic vs rollup is decided by how many distinct franchisor invoice
        numbers the source document references (filename + OCR'd line-item
        descriptions): exactly one => atomic; zero or many => rollup (a batch
        with only week ranges, or a statement enumerating several invoices).

        The bank debit is identified separately: its description is the
        franchisor's pre-auth label ("TAHINIS BUS/ENT"), which shares only the
        'tahinis' token with the "Tahinis Franchising Corp" invoice vendor —
        not 'franchising' — so it needs its own match. It is the cash side of
        the same invoices, not additional spend."""
        for e in expenses:
            e._franchise_role = None  # type: ignore[attr-defined]

        paper = [
            e for e in expenses
            if getattr(e, "_doc_type", None) != "bank_statement"
            and e.document_id is not None
            and _FRANCHISE_VENDOR_TOKEN in self._vendor_tokens(e.vendor_name)
        ]
        for e in expenses:
            if (
                getattr(e, "_doc_type", None) == "bank_statement"
                and "tahinis" in self._vendor_tokens(e.vendor_name)
            ):
                e._franchise_role = "bank"  # type: ignore[attr-defined]

        if not paper:
            return

        doc_ids = {e.document_id for e in paper}
        from app.db.models.document import ExtractedLineItem
        li_rows = await self._db.execute(
            select(ExtractedLineItem.document_id, ExtractedLineItem.description).where(
                ExtractedLineItem.document_id.in_(doc_ids)
            )
        )
        descs_by_doc: dict[uuid.UUID, list[str]] = defaultdict(list)
        for doc_id, desc in li_rows.all():
            if desc:
                descs_by_doc[doc_id].append(desc)

        for e in paper:
            nums = self._franchise_invoice_numbers(
                getattr(e, "_filename", None), descs_by_doc.get(e.document_id, [])
            )
            e._franchise_role = "atomic" if len(nums) == 1 else "rollup"  # type: ignore[attr-defined]

    def _dedup_franchise_rollups(self, expenses: list[Expense]) -> list[Expense]:
        """Collapse franchisor spend onto the atomic per-invoice documents.

        When atomic invoices are present, both other representations of the
        same charges are dropped:
          - statement/batch 'rollup' invoices (re-list the atomics), and
          - the 'bank' pre-auth debits that settle them.
        The atomic invoices carry the correct per-charge amount, week, and
        category (Marketing 2% vs Royalties 5%); the rollups double-count on
        the paper side and the bank debits double-count on the cash side. The
        bank total is not lost — the reconciliation engine cross-checks the
        kept atomic-invoice total against it (unverified_franchise_spend).

        Guard: only collapse when at least one atomic franchisor invoice
        exists. With no atomic invoice, whatever franchise record exists
        (a lone statement, or only bank debits) is the sole evidence of the
        spend and must stay, or franchise Marketing/Royalties would be zeroed."""
        has_atomic = any(getattr(e, "_franchise_role", None) == "atomic" for e in expenses)
        if not has_atomic:
            return expenses
        kept: list[Expense] = []
        for e in expenses:
            role = getattr(e, "_franchise_role", None)
            if role in ("rollup", "bank"):
                logger.info(
                    "pnl_dedup_dropped_franchise_rollup",
                    vendor=e.vendor_name,
                    amount=str(e.amount),
                    filename=getattr(e, "_filename", None),
                    role=role,
                    reason="atomic_invoices_present",
                )
                continue
            kept.append(e)
        return kept

    # Words that carry no vendor identity — bank-description boilerplate,
    # corporate suffixes, generic descriptors. Stripped before token matching.
    _VENDOR_NOISE = frozenset({
        "pre", "authorized", "pre-authorized", "preauthorized", "payment",
        "payments", "pap", "pad", "debit", "credit", "chq", "cheque", "eft",
        "bill", "online", "transfer", "purchase", "pos", "inc", "inc.", "ltd",
        "ltd.", "llc", "corp", "co", "co.", "company", "the", "and", "of",
        "service", "services", "wholesale", "store", "ca", "on", "toronto",
    })

    @classmethod
    def _vendor_tokens(cls, name: str | None) -> frozenset[str]:
        """Significant lowercased tokens for vendor matching. Punctuation
        stripped, boilerplate/noise words removed (e.g. 'Pre-Authorized
        Payment, ALEX FOOD' -> {'alex', 'food'})."""
        if not name:
            return frozenset()
        raw = re.split(r"[^a-z0-9]+", name.lower())
        return frozenset(
            t for t in raw if t and t not in cls._VENDOR_NOISE and len(t) > 1
        )

    @staticmethod
    def _norm_vendor(name: str | None) -> str | None:
        if not name:
            return None
        return " ".join(name.lower().split())

    def _dedup_invoice_vs_bank_by_amount(self, expenses: list[Expense]) -> list[Expense]:
        """Invoice wins for _INVOICE_WINS_CATEGORIES: when a bank-statement
        expense's amount matches an uploaded invoice's amount within tolerance,
        drop the bank line and keep the invoice (the invoice has line-item
        detail the bank description doesn't). A bank line with no matching
        invoice is a real charge with no document yet — it stays, so the
        category isn't silently understated.

        Runs before _dedup_bank_vs_invoice, whose default direction (bank
        wins) is wrong for this category — see _INVOICE_WINS_CATEGORIES.
        """
        invoice_amounts_by_cat: dict[str, list[Decimal]] = {}
        for e in expenses:
            if (
                e.category in _INVOICE_WINS_CATEGORIES
                and getattr(e, "_doc_type", None) != "bank_statement"
                and e.amount is not None
            ):
                invoice_amounts_by_cat.setdefault(e.category, []).append(abs(e.amount))

        kept: list[Expense] = []
        for e in expenses:
            if (
                e.category in _INVOICE_WINS_CATEGORIES
                and getattr(e, "_doc_type", None) == "bank_statement"
                and e.amount is not None
            ):
                target = abs(e.amount)
                tol = max(_ROYALTY_MATCH_ABS, target * _ROYALTY_MATCH_PCT)
                pool = invoice_amounts_by_cat.get(e.category, [])
                match_idx = next(
                    (i for i, inv_amt in enumerate(pool) if abs(inv_amt - target) <= tol), None
                )
                if match_idx is not None:
                    pool.pop(match_idx)  # consume so one invoice can't absorb two bank lines
                    logger.info(
                        "pnl_dedup_dropped_bank_line",
                        category=e.category,
                        amount=str(e.amount),
                        reason="matched_by_uploaded_invoice",
                    )
                    continue
            kept.append(e)
        return kept

    def _dedup_bank_vs_invoice(self, expenses: list[Expense]) -> list[Expense]:
        """Bank statement wins. When a vendor has a bank-statement expense in the
        period, the actual cash already captures that spend, so drop that vendor's
        uploaded-invoice/receipt expenses to avoid double-counting (e.g. Alex Food
        invoices + the bank payment to Alex).

        Vendor identity matched on significant-token overlap, not substring:
        bank descriptions ('Pre-Authorized Payment, ALEX FOOD') and invoice
        vendor names ('Alex Food Service') rarely contain one another but share
        identifying tokens ({'alex','food'})."""
        bank_token_sets = [
            self._vendor_tokens(e.vendor_name)
            for e in expenses
            if getattr(e, "_doc_type", None) == "bank_statement" and e.vendor_name
        ]
        bank_token_sets = [s for s in bank_token_sets if s]
        if not bank_token_sets:
            return expenses

        def _matches_bank(inv: frozenset[str]) -> bool:
            if not inv:
                return False
            for bank in bank_token_sets:
                shared = inv & bank
                # subset (one fully contained) or >=2 identifying tokens shared
                if shared and (inv <= bank or bank <= inv or len(shared) >= 2):
                    return True
            return False

        kept: list[Expense] = []
        for e in expenses:
            if getattr(e, "_doc_type", None) == "bank_statement":
                kept.append(e)
                continue
            if _matches_bank(self._vendor_tokens(e.vendor_name)):
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
