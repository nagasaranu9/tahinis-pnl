import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repositories.document_repo import (
    DocumentRepository,
    _extract_invoice_number,
    _vendor_tokens,
)


def test_vendor_tokens_strips_noise_and_case() -> None:
    assert _vendor_tokens("Alex Food Service Corp.") == {"alex", "food", "service"}
    assert _vendor_tokens("ALEX FOOD SERVICE") == {"alex", "food", "service"}


def test_vendor_tokens_empty_for_none_or_blank() -> None:
    assert _vendor_tokens(None) == frozenset()
    assert _vendor_tokens("") == frozenset()


def test_extract_invoice_number_matches_common_patterns() -> None:
    assert _extract_invoice_number("Invoice_INV019553_from_Alex_Food_Service.pdf") == "19553"
    assert _extract_invoice_number("INV-021842.pdf") == "21842"


def test_extract_invoice_number_none_when_absent() -> None:
    assert _extract_invoice_number("1941 Tahinis Franchising Invoice Jan-Mar 2026.pdf") is None
    assert _extract_invoice_number(None) is None


def _fake_document(*, doc_id: uuid.UUID, filename: str, vendor_name: str) -> MagicMock:
    doc = MagicMock()
    doc.id = doc_id
    doc.original_filename = filename
    doc.vendor_name = vendor_name
    return doc


def _repo_with_candidates(candidates: list[MagicMock]) -> DocumentRepository:
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = candidates
    db.execute = AsyncMock(return_value=result)
    return DocumentRepository(db)


async def test_find_content_duplicate_matches_cross_channel_same_invoice() -> None:
    original_id = uuid.uuid4()
    candidate = _fake_document(
        doc_id=original_id,
        filename="Invoice_INV019553_from_Alex_Food_Service.pdf",
        vendor_name="Alex Food Service Corp.",
    )
    repo = _repo_with_candidates([candidate])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="Invoice_INV019553_from_Alex_Food_Service (1).pdf",
        vendor_name="Alex Food Service",
        document_date=datetime(2026, 6, 1, tzinfo=UTC),
        total_amount=Decimal("542.10"),
    )
    assert match is not None
    assert match.id == original_id


async def test_find_content_duplicate_vetoes_differing_invoice_numbers() -> None:
    candidate = _fake_document(
        doc_id=uuid.uuid4(),
        filename="Invoice_INV017704_from_Alex_Food_Service.pdf",
        vendor_name="Alex Food Service",
    )
    repo = _repo_with_candidates([candidate])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="Invoice_INV017712_from_Alex_Food_Service.pdf",
        vendor_name="Alex Food Service",
        document_date=datetime(2026, 6, 1, tzinfo=UTC),
        total_amount=Decimal("300.00"),
    )
    assert match is None, "different invoice numbers must never be collapsed, even same vendor/date/amount"


async def test_find_content_duplicate_falls_back_when_no_invoice_number_extractable() -> None:
    candidate = _fake_document(
        doc_id=uuid.uuid4(),
        filename="1941 Tahinis Franchising Invoice Jan-Mar 2026.pdf",
        vendor_name="Tahinis Franchising Corp",
    )
    repo = _repo_with_candidates([candidate])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="1941 Tahinis Franchising Invoice Jan-Mar 2026 (1).pdf",
        vendor_name="Tahinis Franchising",
        document_date=datetime(2026, 6, 1, tzinfo=UTC),
        total_amount=Decimal("4546.22"),
    )
    assert match is not None
    assert match.id == candidate.id


async def test_find_content_duplicate_ignores_different_vendor() -> None:
    candidate = _fake_document(
        doc_id=uuid.uuid4(),
        filename="Invoice_INV999_from_Some_Other_Vendor.pdf",
        vendor_name="Some Other Vendor",
    )
    repo = _repo_with_candidates([candidate])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="Invoice_INV001_from_Alex_Food_Service.pdf",
        vendor_name="Alex Food Service",
        document_date=datetime(2026, 6, 1, tzinfo=UTC),
        total_amount=Decimal("100.00"),
    )
    assert match is None


async def test_find_content_duplicate_returns_none_when_no_candidates() -> None:
    repo = _repo_with_candidates([])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="Invoice_INV001_from_Alex_Food_Service.pdf",
        vendor_name="Alex Food Service",
        document_date=datetime(2026, 6, 1, tzinfo=UTC),
        total_amount=Decimal("100.00"),
    )
    assert match is None


@pytest.mark.parametrize(
    "vendor_name,document_date,total_amount",
    [
        (None, datetime(2026, 6, 1, tzinfo=UTC), Decimal("10.00")),
        ("Vendor", None, Decimal("10.00")),
        ("Vendor", datetime(2026, 6, 1, tzinfo=UTC), None),
    ],
)
async def test_find_content_duplicate_returns_none_when_fields_missing(
    vendor_name: str | None, document_date: datetime | None, total_amount: Decimal | None
) -> None:
    repo = _repo_with_candidates([])
    match = await repo.find_content_duplicate(
        uuid.uuid4(),
        exclude_document_id=uuid.uuid4(),
        original_filename="whatever.pdf",
        vendor_name=vendor_name,
        document_date=document_date,
        total_amount=total_amount,
    )
    assert match is None


async def test_mark_duplicate_sets_fields() -> None:
    db = MagicMock()
    db.execute = AsyncMock()
    repo = DocumentRepository(db)
    original_id = uuid.uuid4()
    dup_id = uuid.uuid4()
    await repo.mark_duplicate(dup_id, duplicate_of=original_id)
    db.execute.assert_awaited_once()
    stmt = db.execute.await_args.args[0]
    compiled = stmt.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled)
    assert "is_duplicate=true" in sql.lower()
    assert "status" in sql.lower()
    assert "Duplicate of existing document" in sql
