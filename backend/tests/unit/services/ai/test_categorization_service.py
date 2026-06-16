"""Unit tests for CategorizationService — mocks Anthropic SDK."""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.ai.categorization_service import CategorizationService
from app.db.models.expense import EXPENSE_CATEGORIES


def _make_mock_response(category: str, confidence: float, explanation: str) -> MagicMock:
    content_block = MagicMock()
    content_block.text = json.dumps({
        "category": category,
        "confidence": confidence,
        "explanation": explanation,
    })
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.mark.asyncio
async def test_categorize_food_cost():
    with patch("app.services.ai.categorization_service.anthropic.Anthropic") as MockClient:
        mock_response = _make_mock_response("Food Cost", 0.95, "Sysco is a food distributor.")
        MockClient.return_value.messages.create.return_value = mock_response

        svc = CategorizationService()
        result = await svc.categorize(
            vendor_name="Sysco Canada",
            amount=Decimal("1200.00"),
            currency_code="CAD",
        )

    assert result.category == "Food Cost"
    assert result.confidence == Decimal("0.9500")
    assert "Sysco" in result.explanation


@pytest.mark.asyncio
async def test_categorize_unknown_category_defaults_to_miscellaneous():
    with patch("app.services.ai.categorization_service.anthropic.Anthropic") as MockClient:
        mock_response = _make_mock_response("Office Supplies", 0.90, "Irrelevant category.")
        MockClient.return_value.messages.create.return_value = mock_response

        svc = CategorizationService()
        result = await svc.categorize(vendor_name="Staples", amount=Decimal("50.00"), currency_code="CAD")

    assert result.category == "Miscellaneous"


@pytest.mark.asyncio
async def test_categorize_handles_api_exception():
    with patch("app.services.ai.categorization_service.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = RuntimeError("API down")

        svc = CategorizationService()
        result = await svc.categorize(vendor_name="Vendor", amount=Decimal("100.00"), currency_code="CAD")

    assert result.category == "Miscellaneous"
    assert result.confidence == Decimal("0.00")


@pytest.mark.asyncio
async def test_categorize_handles_invalid_json():
    with patch("app.services.ai.categorization_service.anthropic.Anthropic") as MockClient:
        content_block = MagicMock()
        content_block.text = "not json at all"
        msg = MagicMock()
        msg.content = [content_block]
        MockClient.return_value.messages.create.return_value = msg

        svc = CategorizationService()
        result = await svc.categorize(vendor_name="Vendor", amount=Decimal("100.00"), currency_code="CAD")

    assert result.category == "Miscellaneous"
    assert result.confidence == Decimal("0.00")


@pytest.mark.asyncio
async def test_all_categories_valid():
    """Ensure EXPENSE_CATEGORIES set is non-empty and matches expected count."""
    assert len(EXPENSE_CATEGORIES) == 14
    assert "Food Cost" in EXPENSE_CATEGORIES
    assert "Payroll" in EXPENSE_CATEGORIES
    assert "Miscellaneous" in EXPENSE_CATEGORIES


def test_parse_response_all_valid_categories():
    svc = CategorizationService()
    for cat in EXPENSE_CATEGORIES:
        result = svc._parse_response(json.dumps({"category": cat, "confidence": 0.85, "explanation": "test"}))
        assert result.category == cat
