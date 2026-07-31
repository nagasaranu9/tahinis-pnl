"""Bank-statement-basis P&L (tenant-elected model).

Everything is computed from the bank statement, nothing else:

  * Revenue      = money IN — every sales CREDIT line (BankDeposit.is_revenue).
                   This is what actually lands in the account each month, which
                   is the number the owners reconcile against.
  * Expenses     = money OUT — bank-statement-sourced Expense rows, categorized.
                   PushOps API labour is ignored; labour = the bank's payroll
                   debits + all cash withdrawals (staffing). Franchise cost = the
                   bank's franchise debits (not the overlapping invoices).
  * Excluded     = loan principal (balance-sheet), credit-card payoff transfers
                   (their purchases are counted directly), delivery commissions
                   (deposits are already net of the platform cut), and the
                   non-P&L buckets (personal / owner draw / shareholder loan).

HST is shown two ways:
  * Before HST — figures as they hit the bank, HST still inside them.
  * After HST  — HST collected on sales removed, input tax credits (ITC) on
                 taxable purchases removed; the difference between the two net
                 profits is the net HST you remit to CRA.

Partner split applies to both the top line (revenue) and the bottom line (net
profit), for both HST bases, using the tenant's PartnerShare config.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.bank_deposit import BankDeposit
from app.db.models.document import Document
from app.db.models.expense import NON_PNL_CATEGORIES, Expense
from app.db.models.partner_share import PartnerShare

logger = structlog.get_logger(__name__)

_CENTS = Decimal("0.01")
# Ontario HST. Sales deposits and taxable purchases are tax-INCLUSIVE, so the
# embedded tax = amount * rate / (1 + rate).
_HST_RATE = Decimal("0.13")
_HST_FRACTION = _HST_RATE / (Decimal("1") + _HST_RATE)  # 13/113

_COGS_CATEGORIES = {"Food Cost", "Beverage Cost", "Packaging"}
_LABOR_CATEGORIES = {"Payroll"}

# Categories carrying claimable HST (input tax credits). Basic groceries (Food
# Cost) are zero-rated and Insurance/Payroll are exempt, so they yield no ITC —
# never derive a phantom 13% on them.
_HST_TAXABLE_CATEGORIES = {
    "Rent", "Marketing", "Software", "Utilities", "Maintenance", "Repairs",
    "Professional Services", "Beverage Cost", "Royalties", "Miscellaneous",
}

# Categories that never belong on the bank-basis P&L.
_EXCLUDED_CATEGORIES = set(NON_PNL_CATEGORIES) | {"Delivery Commissions"}

# Vendor markers for bank lines that are NOT operating cost:
#   loan principal  — repaying borrowed money is a balance-sheet movement
#   cc payoff       — paying the Mastercard; its purchases are counted directly
_PRINCIPAL_MARKERS = ("standing order", "loan payment", "spl lns")
_CC_PAYOFF_MARKERS = ("credit card payment",)
# Interest is a real financing cost but sits BELOW EBITDA.
_INTEREST_MARKERS = ("interest paid", "interest charge")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _vendor(exp: Expense) -> str:
    return (exp.vendor_name or "").lower()


class BankPnLCalculator:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def compute(
        self,
        tenant_id: uuid.UUID,
        period_start: datetime,
        period_end: datetime,
    ) -> dict:
        # ---- Revenue: sales deposits (money in) ----
        rev_rows = (await self._db.execute(
            select(BankDeposit.channel, func.coalesce(func.sum(BankDeposit.amount), 0))
            .where(and_(
                BankDeposit.tenant_id == tenant_id,
                BankDeposit.is_revenue.is_(True),
                BankDeposit.deposit_date >= period_start,
                BankDeposit.deposit_date <= period_end,
            )).group_by(BankDeposit.channel)
        )).all()
        revenue_by_channel = {ch: _q(Decimal(str(amt))) for ch, amt in rev_rows}
        revenue = _q(sum(revenue_by_channel.values(), Decimal("0")))

        # ---- Expenses: bank-statement-sourced, categorized ----
        exp_rows = (await self._db.execute(
            select(Expense).join(Document, Expense.document_id == Document.id).where(and_(
                Expense.tenant_id == tenant_id,
                Expense.expense_date >= period_start,
                Expense.expense_date <= period_end,
                Document.document_type == "bank_statement",
            ))
        )).scalars().all()

        cogs = labor = opex = interest = principal_excluded = Decimal("0")
        itc = Decimal("0")
        cat_totals: dict[str, Decimal] = {}
        for e in exp_rows:
            if e.amount is None:
                continue
            cat = e.category or "Uncategorized"
            if cat in _EXCLUDED_CATEGORIES:
                continue
            v = _vendor(e)
            # Loan principal + CC payoff transfers are not operating cost.
            if any(m in v for m in _PRINCIPAL_MARKERS) or any(m in v for m in _CC_PAYOFF_MARKERS):
                principal_excluded += e.amount
                continue
            # Interest → below-EBITDA financing line.
            if any(m in v for m in _INTEREST_MARKERS):
                interest += e.amount
                continue

            amount = e.amount
            cat_totals[cat] = cat_totals.get(cat, Decimal("0")) + amount
            if cat in _COGS_CATEGORIES:
                cogs += amount
            elif cat in _LABOR_CATEGORIES:
                labor += amount
            else:
                opex += amount
            # ITC on taxable purchases (tax-inclusive → embedded 13/113).
            if cat in _HST_TAXABLE_CATEGORIES:
                itc += amount * _HST_FRACTION

        cogs, labor, opex, interest = _q(cogs), _q(labor), _q(opex), _q(interest)
        itc = _q(itc)

        # ---- HST ----
        hst_collected = _q(revenue * _HST_FRACTION)
        net_hst_remittance = _q(hst_collected - itc)

        # ---- Before-HST P&L (cash as banked) ----
        ebitda_before = _q(revenue - cogs - labor - opex)
        net_before = _q(ebitda_before - interest)

        # ---- After-HST P&L (HST stripped from sales + ITC removed from cost) ----
        revenue_after = _q(revenue - hst_collected)
        net_after = _q(net_before - net_hst_remittance)
        ebitda_after = _q(ebitda_before - hst_collected + itc)

        # ---- Partner splits ----
        partners = (await self._db.execute(
            select(PartnerShare).where(PartnerShare.tenant_id == tenant_id)
            .order_by(PartnerShare.sort_order, PartnerShare.name)
        )).scalars().all()
        pct_total = sum((p.share_pct for p in partners), Decimal("0")) or Decimal("100")
        partner_split = []
        for p in partners:
            frac = p.share_pct / pct_total
            partner_split.append({
                "name": p.name,
                "share_pct": _q(p.share_pct),
                "revenue_before_hst": _q(revenue * frac),
                "revenue_after_hst": _q(revenue_after * frac),
                "net_before_hst": _q(net_before * frac),
                "net_after_hst": _q(net_after * frac),
            })

        return {
            "period_start": period_start.date().isoformat(),
            "period_end": period_end.date().isoformat(),
            "basis": "bank_statement",
            "revenue": revenue,
            "revenue_by_channel": revenue_by_channel,
            "cogs": cogs,
            "labor": labor,
            "operating_expenses": opex,
            "interest": interest,
            "expense_by_category": {k: _q(v) for k, v in cat_totals.items()},
            "principal_excluded": _q(principal_excluded),
            "before_hst": {
                "revenue": revenue,
                "ebitda": ebitda_before,
                "net_profit": net_before,
            },
            "after_hst": {
                "revenue": revenue_after,
                "ebitda": ebitda_after,
                "net_profit": net_after,
            },
            "hst": {
                "collected_on_sales": hst_collected,
                "input_tax_credits": itc,
                "net_remittance": net_hst_remittance,
            },
            "partner_split": partner_split,
        }
