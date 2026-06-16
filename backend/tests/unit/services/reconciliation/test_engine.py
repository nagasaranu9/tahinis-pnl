"""Unit tests for the ReconciliationEngine flagging logic.

Uses in-memory objects — no DB required. The engine methods that call the DB
(_load_documents, _load_expenses, etc.) are patched so we can drive each
flag path in isolation.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.document import Document
from app.db.models.expense import Expense
from app.db.models.toast import ToastOrder
from app.db.models.reconciliation import ReconciliationRun
from app.services.reconciliation.engine import (
    ANOMALY_STDDEV_THRESHOLD,
    MIN_VENDOR_SAMPLES,
    ReconciliationEngine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = uuid.uuid4()
RUN_ID = uuid.uuid4()
PERIOD_START = datetime(2024, 6, 1, tzinfo=timezone.utc)
PERIOD_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=timezone.utc)


def _make_engine() -> tuple[ReconciliationEngine, MagicMock]:
    """Return engine with mocked DB session and repo."""
    db = AsyncMock()
    engine = ReconciliationEngine(db)
    repo_mock = AsyncMock()
    engine._repo = repo_mock
    return engine, repo_mock


def _doc(
    *,
    is_duplicate: bool = False,
    duplicate_of: uuid.UUID | None = None,
    filename: str = "invoice.pdf",
    location_id: uuid.UUID | None = None,
) -> Document:
    d = MagicMock(spec=Document)
    d.id = uuid.uuid4()
    d.is_duplicate = is_duplicate
    d.duplicate_of = duplicate_of
    d.original_filename = filename
    d.location_id = location_id
    d.tenant_id = TENANT_ID
    d.created_at = PERIOD_START
    return d


def _expense(
    *,
    category: str | None = "Food Cost",
    amount: Decimal = Decimal("500.00"),
    vendor_name: str | None = "Sysco Canada",
    document_id: uuid.UUID | None = None,
    created_at: datetime = PERIOD_START,
) -> Expense:
    e = MagicMock(spec=Expense)
    e.id = uuid.uuid4()
    e.tenant_id = TENANT_ID
    e.category = category
    e.amount = amount
    e.vendor_name = vendor_name
    e.document_id = document_id
    e.created_at = created_at
    return e


def _order(
    *,
    business_date: str = "20240615",
    net_amount: Decimal = Decimal("1200.00"),
    is_void: bool = False,
) -> ToastOrder:
    o = MagicMock(spec=ToastOrder)
    o.id = uuid.uuid4()
    o.tenant_id = TENANT_ID
    o.business_date = business_date
    o.net_amount = net_amount
    o.is_void = is_void
    o.closed_at = PERIOD_START
    return o


async def _run_execute(
    engine: ReconciliationEngine,
    documents: list,
    expenses: list,
    toast_orders: list,
    vendor_amounts: dict | None = None,
) -> dict:
    """Patch all DB loaders and run _execute."""
    engine._load_documents = AsyncMock(return_value=documents)
    engine._load_expenses = AsyncMock(return_value=expenses)
    engine._load_toast_orders = AsyncMock(return_value=toast_orders)
    engine._load_vendor_amount_history = AsyncMock(
        return_value=vendor_amounts if vendor_amounts is not None else defaultdict(list)
    )
    return await engine._execute(RUN_ID, TENANT_ID, PERIOD_START, PERIOD_END, None)


# ---------------------------------------------------------------------------
# Flag: duplicate_invoice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_invoice_flag_raised():
    engine, repo = _make_engine()
    dup_doc = _doc(is_duplicate=True, duplicate_of=uuid.uuid4())
    normal_doc = _doc(is_duplicate=False)

    result = await _run_execute(engine, [dup_doc, normal_doc], [], [])

    assert result["flags_raised"] == 1
    repo.create_flag.assert_awaited_once()
    call_kwargs = repo.create_flag.call_args.kwargs
    assert call_kwargs["flag_type"] == "duplicate_invoice"
    assert call_kwargs["severity"] == "high"
    assert call_kwargs["document_id"] == dup_doc.id


@pytest.mark.asyncio
async def test_no_duplicate_invoice_flag_when_clean():
    engine, repo = _make_engine()
    result = await _run_execute(engine, [_doc()], [], [])

    assert result["flags_raised"] == 0
    repo.create_flag.assert_not_awaited()


# ---------------------------------------------------------------------------
# Flag: duplicate_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_expense_flag_raised_for_multiple_expenses_per_doc():
    engine, repo = _make_engine()
    doc_id = uuid.uuid4()
    exp_a = _expense(document_id=doc_id)
    exp_b = _expense(document_id=doc_id)

    result = await _run_execute(engine, [], [exp_a, exp_b], [])

    # One flag per expense record for the duplicate group = 2 flags
    assert result["flags_raised"] == 2
    for call in repo.create_flag.call_args_list:
        assert call.kwargs["flag_type"] == "duplicate_expense"
        assert call.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_no_duplicate_expense_flag_for_single_expense_per_doc():
    engine, repo = _make_engine()
    doc_id = uuid.uuid4()
    exp = _expense(document_id=doc_id)

    result = await _run_execute(engine, [], [exp], [])

    # No duplicate_expense flags
    for call in repo.create_flag.call_args_list:
        assert call.kwargs["flag_type"] != "duplicate_expense"


@pytest.mark.asyncio
async def test_no_duplicate_expense_flag_for_expenses_without_doc():
    engine, repo = _make_engine()
    # Two expenses with no document_id should NOT trigger duplicate_expense
    exp_a = _expense(document_id=None)
    exp_b = _expense(document_id=None)

    result = await _run_execute(engine, [], [exp_a, exp_b], [])

    for call in repo.create_flag.call_args_list:
        assert call.kwargs["flag_type"] != "duplicate_expense"


# ---------------------------------------------------------------------------
# Flag: uncategorized_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uncategorized_expense_flag_raised():
    engine, repo = _make_engine()
    exp = _expense(category=None)

    result = await _run_execute(engine, [], [exp], [])

    assert result["flags_raised"] == 1
    call_kwargs = repo.create_flag.call_args.kwargs
    assert call_kwargs["flag_type"] == "uncategorized_expense"
    assert call_kwargs["severity"] == "medium"
    assert call_kwargs["expense_id"] == exp.id


@pytest.mark.asyncio
async def test_categorized_expense_no_flag():
    engine, repo = _make_engine()
    exp = _expense(category="Food Cost")

    result = await _run_execute(engine, [], [exp], [])

    assert result["flags_raised"] == 0


# ---------------------------------------------------------------------------
# Flag: suspicious_amount (z-score anomaly)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspicious_amount_flag_raised_when_z_score_exceeds_threshold():
    engine, repo = _make_engine()
    vendor = "Sysco Canada"

    # Build history: 10 samples tightly clustered around 500
    history = [Decimal("500.00")] * 9 + [Decimal("510.00")]
    # Expense with amount 10× normal → z-score >> 3
    exp = _expense(vendor_name=vendor, amount=Decimal("5000.00"), category="Food Cost")

    result = await _run_execute(engine, [], [exp], [], vendor_amounts={vendor: history})

    assert result["flags_raised"] == 1
    call_kwargs = repo.create_flag.call_args.kwargs
    assert call_kwargs["flag_type"] == "suspicious_amount"
    assert call_kwargs["severity"] == "high"


@pytest.mark.asyncio
async def test_suspicious_amount_not_flagged_when_normal():
    engine, repo = _make_engine()
    vendor = "Sysco Canada"

    history = [Decimal("500.00")] * 10
    exp = _expense(vendor_name=vendor, amount=Decimal("495.00"), category="Food Cost")

    result = await _run_execute(engine, [], [exp], [], vendor_amounts={vendor: history})

    assert result["flags_raised"] == 0


@pytest.mark.asyncio
async def test_suspicious_amount_skipped_below_min_samples():
    engine, repo = _make_engine()
    vendor = "Tiny Vendor"
    # Only 3 samples — below MIN_VENDOR_SAMPLES (5)
    history = [Decimal("10.00"), Decimal("20.00"), Decimal("30.00")]
    exp = _expense(vendor_name=vendor, amount=Decimal("99999.00"), category="Food Cost")

    result = await _run_execute(engine, [], [exp], [], vendor_amounts={vendor: history})

    assert result["flags_raised"] == 0


@pytest.mark.asyncio
async def test_suspicious_amount_skipped_for_missing_vendor_name():
    engine, repo = _make_engine()
    exp = _expense(vendor_name=None, amount=Decimal("5000.00"), category="Food Cost")

    result = await _run_execute(engine, [], [exp], [])

    assert result["flags_raised"] == 0


@pytest.mark.asyncio
async def test_suspicious_amount_skipped_when_stddev_is_zero():
    """Uniform amounts give stdev=0 → skip division to avoid false positives."""
    engine, repo = _make_engine()
    vendor = "Uniform Vendor"
    history = [Decimal("500.00")] * 10  # stdev == 0
    exp = _expense(vendor_name=vendor, amount=Decimal("501.00"), category="Food Cost")

    result = await _run_execute(engine, [], [exp], [], vendor_amounts={vendor: history})

    assert result["flags_raised"] == 0


# ---------------------------------------------------------------------------
# Flag: unmatched_sale
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unmatched_sale_flag_raised_when_no_expense_for_toast_date():
    engine, repo = _make_engine()
    order = _order(business_date="20240615", net_amount=Decimal("1200.00"))

    # No expenses → no expense_dates → every toast date is unmatched
    result = await _run_execute(engine, [], [], [order])

    assert result["flags_raised"] == 1
    call_kwargs = repo.create_flag.call_args.kwargs
    assert call_kwargs["flag_type"] == "unmatched_sale"
    assert call_kwargs["severity"] == "medium"


@pytest.mark.asyncio
async def test_unmatched_sale_not_flagged_when_expense_present():
    engine, repo = _make_engine()
    doc_id = uuid.uuid4()
    # Expense created on same day as the Toast order business_date
    created_at = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
    exp = _expense(document_id=doc_id, category="Food Cost", created_at=created_at)
    order = _order(business_date="20240615", net_amount=Decimal("1200.00"))

    result = await _run_execute(engine, [], [exp], [order])

    # unmatched_sale should NOT fire; expense date matches
    for call in repo.create_flag.call_args_list:
        assert call.kwargs["flag_type"] != "unmatched_sale"


@pytest.mark.asyncio
async def test_unmatched_sale_not_flagged_for_void_orders():
    engine, repo = _make_engine()
    voided = _order(business_date="20240615", net_amount=Decimal("1200.00"), is_void=True)

    result = await _run_execute(engine, [], [], [voided])

    # Void orders excluded from Toast date aggregation
    for call in repo.create_flag.call_args_list:
        assert call.kwargs["flag_type"] != "unmatched_sale"


@pytest.mark.asyncio
async def test_unmatched_sale_not_flagged_when_net_amount_is_zero():
    engine, repo = _make_engine()
    zero_order = _order(business_date="20240615", net_amount=Decimal("0.00"))

    result = await _run_execute(engine, [], [], [zero_order])

    assert result["flags_raised"] == 0


# ---------------------------------------------------------------------------
# Aggregate counters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_result_counters_reflect_loaded_data():
    engine, repo = _make_engine()
    docs = [_doc(), _doc()]
    exps = [_expense(category="Food Cost"), _expense(category="Cleaning")]
    orders = [_order()]

    result = await _run_execute(engine, docs, exps, orders)

    assert result["documents_checked"] == 2
    assert result["expenses_checked"] == 2
    assert result["toast_orders_checked"] == 1


@pytest.mark.asyncio
async def test_total_sales_excludes_void_orders():
    engine, repo = _make_engine()
    active = _order(net_amount=Decimal("800.00"), is_void=False)
    voided = _order(net_amount=Decimal("200.00"), is_void=True)

    result = await _run_execute(engine, [], [], [active, voided])

    assert result["total_sales_amount"] == Decimal("800.00")


@pytest.mark.asyncio
async def test_total_expense_amount_sums_correctly():
    engine, repo = _make_engine()
    exps = [
        _expense(amount=Decimal("100.00"), category="Food Cost"),
        _expense(amount=Decimal("50.00"), category="Cleaning"),
    ]

    result = await _run_execute(engine, [], exps, [])

    assert result["total_expense_amount"] == Decimal("150.00")


@pytest.mark.asyncio
async def test_total_sales_none_when_no_orders():
    engine, repo = _make_engine()
    result = await _run_execute(engine, [], [], [])
    # sum of empty = Decimal("0") which becomes None via `or None`
    assert result["total_sales_amount"] is None


# ---------------------------------------------------------------------------
# Constants guard
# ---------------------------------------------------------------------------


def test_anomaly_threshold_values():
    assert ANOMALY_STDDEV_THRESHOLD == 3
    assert MIN_VENDOR_SAMPLES == 5
