"""Unit tests for franchisor statement/batch rollup dedup in the P&L calculator.

The franchisor (Tahinis Franchising Corp) bills the same weekly charges through
atomic per-invoice PDFs, periodic statements that re-list those invoices, and
monthly batch files — plus the pre-authorized bank debit that settles them.
Counting all of them multiplies franchise Marketing/Royalties. These tests pin
the dedup that keeps only the atomic invoices.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.pnl.calculator import PnLCalculator


def _exp(amount, *, role=None, doc_type="invoice", vendor="Tahinis Franchising Corp.", category="Marketing"):
    e = SimpleNamespace(
        id=uuid.uuid4(), amount=Decimal(str(amount)), vendor_name=vendor,
        category=category, document_id=uuid.uuid4(),
    )
    e._doc_type = doc_type
    e._filename = None
    e._franchise_role = role
    return e


def _calc() -> PnLCalculator:
    return PnLCalculator(MagicMock())


# ---- _franchise_invoice_numbers (pure) ----

def test_invoice_numbers_from_filename():
    nums = PnLCalculator._franchise_invoice_numbers("Invoice_21284_from_Tahinis_Franchising_Corp.pdf", [])
    assert nums == {"21284"}


def test_invoice_numbers_from_statement_line_items():
    nums = PnLCalculator._franchise_invoice_numbers(
        "Statement_6772_from_Tahinis_Franchising_Corp.pdf",
        ["Invoice #20779: Due 2026/06/30", "Invoice #21284: Marketing", "Invoice #21213: Royalties"],
    )
    assert nums == {"20779", "21284", "21213"}


def test_invoice_numbers_batch_with_only_week_ranges_has_none():
    nums = PnLCalculator._franchise_invoice_numbers(
        "1941 Tahinis Corp Invoices.pdf",
        ["Marketing - June 22-28 (Week 26)", "Royalties - June 15-21 (Week 25)"],
    )
    assert nums == set()


def test_invoice_numbers_handles_inv_dash_format():
    assert PnLCalculator._franchise_invoice_numbers("INV-020768.pdf", []) == {"20768"}


# ---- _dedup_franchise_rollups ----

def test_rollups_and_bank_dropped_when_atomic_present():
    atomic_m = _exp("540.65", role="atomic", category="Marketing")
    atomic_r = _exp("1351.62", role="atomic", category="Royalties")
    statement = _exp("2449.24", role="rollup", category="Marketing")
    batch = _exp("676.37", role="rollup", category="Marketing")
    bank = _exp("1506.81", role="bank", doc_type="bank_statement",
                vendor="Pre-Authorized Payment, TAHINIS BUS/ENT", category="Royalties")
    kept = _calc()._dedup_franchise_rollups([atomic_m, atomic_r, statement, batch, bank])
    assert set(id(e) for e in kept) == {id(atomic_m), id(atomic_r)}


def test_rollups_kept_when_no_atomic_present():
    # Only a statement and a bank line — the sole evidence of the spend.
    statement = _exp("2449.24", role="rollup", category="Marketing")
    bank = _exp("1506.81", role="bank", doc_type="bank_statement", category="Royalties")
    kept = _calc()._dedup_franchise_rollups([statement, bank])
    assert kept == [statement, bank]


def test_non_franchise_expenses_untouched():
    atomic = _exp("540.65", role="atomic", category="Marketing")
    google_ads = _exp("20.10", role=None, vendor="5$ Shawarma (google_ads)", category="Marketing")
    food = _exp("4669.90", role=None, doc_type="bank_statement",
                vendor="Pre-Authorized Payment, ALEX FOOD BUS/ENT", category="Food Cost")
    kept = _calc()._dedup_franchise_rollups([atomic, google_ads, food])
    assert google_ads in kept and food in kept and atomic in kept
