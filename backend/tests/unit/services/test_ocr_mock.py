import asyncio
from decimal import Decimal

import pytest

from app.services.ocr.mock_adapter import MockOCRAdapter


@pytest.mark.asyncio
async def test_mock_returns_result() -> None:
    adapter = MockOCRAdapter()
    result = await adapter.process(b"%PDF-fake-content", "application/pdf")
    assert result.provider == "mock"
    assert result.extracted_text
    assert result.confidence_score > Decimal("0.9")
    assert len(result.line_items) > 0
    assert result.total_amount is not None
    assert result.total_amount > Decimal("0")


@pytest.mark.asyncio
async def test_mock_deterministic() -> None:
    """Same file bytes always returns same fixture."""
    adapter = MockOCRAdapter()
    content = b"deterministic-test-content"
    r1 = await adapter.process(content, "application/pdf")
    r2 = await adapter.process(content, "application/pdf")
    assert r1.vendor_name == r2.vendor_name
    assert r1.total_amount == r2.total_amount


@pytest.mark.asyncio
async def test_mock_line_items_have_valid_amounts() -> None:
    adapter = MockOCRAdapter()
    result = await adapter.process(b"%PDF-test", "application/pdf")
    for item in result.line_items:
        assert item.amount > Decimal("0"), f"Line item amount must be positive: {item}"
        assert Decimal("0") <= item.confidence_score <= Decimal("1")
