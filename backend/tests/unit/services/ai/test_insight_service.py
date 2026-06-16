"""Unit tests for AIInsightService.

Mocks anthropic.Anthropic to avoid real API calls.
"""
import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.db.models.ai_insight import INSIGHT_TYPES
from app.services.ai.insight_service import AIInsightService, InsightContextBuilder


def _make_service() -> AIInsightService:
    with patch("app.services.ai.insight_service.anthropic.Anthropic"):
        svc = AIInsightService()
    return svc


def _mock_response(payload: dict, model: str = "claude-sonnet-4-6") -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    msg.model = model
    return msg


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_generate_pnl_summary_happy_path():
    svc = _make_service()
    payload = {
        "insight_type": "pnl_summary",
        "severity": "info",
        "title": "Strong June Performance",
        "summary": "Net revenue up 12% versus prior month.",
        "explanation": "Revenue grew due to higher weekend covers.",
        "confidence_score": 0.88,
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("pnl_summary", {"net_revenue": "5000"}, "2024-06-01", "2024-06-30")

    assert result.insight_type == "pnl_summary"
    assert result.severity == "info"
    assert result.title == "Strong June Performance"
    assert result.confidence_score == Decimal("0.8800")


def test_generate_category_analysis_critical_severity():
    svc = _make_service()
    payload = {
        "insight_type": "category_analysis",
        "severity": "critical",
        "title": "Food Cost Exceeds 40%",
        "summary": "Food cost at 42% — above industry standard of 35%.",
        "explanation": "High protein costs driving COGS up.",
        "confidence_score": 0.95,
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("category_analysis", {}, "2024-06-01", "2024-06-30")

    assert result.severity == "critical"
    assert result.confidence_score == Decimal("0.9500")


# ---------------------------------------------------------------------------
# Invalid / edge-case responses
# ---------------------------------------------------------------------------


def test_unknown_insight_type_falls_back_to_requested_type():
    svc = _make_service()
    payload = {
        "insight_type": "totally_invalid_type",
        "severity": "info",
        "title": "Test",
        "summary": "Test",
        "explanation": "Test",
        "confidence_score": 0.7,
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")
    # Falls back to requested type
    assert result.insight_type == "pnl_summary"


def test_unknown_severity_falls_back_to_info():
    svc = _make_service()
    payload = {
        "insight_type": "pnl_summary",
        "severity": "extreme",  # invalid
        "title": "Test",
        "summary": "Test",
        "explanation": "Test",
        "confidence_score": 0.5,
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")
    assert result.severity == "info"


def test_confidence_score_clamped_above_one():
    svc = _make_service()
    payload = {
        "insight_type": "pnl_summary",
        "severity": "info",
        "title": "T",
        "summary": "S",
        "explanation": "E",
        "confidence_score": 1.5,  # over 1.0
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")
    assert result.confidence_score <= Decimal("1.0")


def test_confidence_score_clamped_below_zero():
    svc = _make_service()
    payload = {
        "insight_type": "pnl_summary",
        "severity": "info",
        "title": "T",
        "summary": "S",
        "explanation": "E",
        "confidence_score": -0.5,
    }
    svc._client.messages.create.return_value = _mock_response(payload)

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")
    assert result.confidence_score >= Decimal("0.0")


def test_api_exception_returns_zero_confidence_fallback():
    svc = _make_service()
    svc._client.messages.create.side_effect = Exception("API timeout")

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")

    assert result.confidence_score == Decimal("0.00")
    assert result.insight_type == "pnl_summary"
    assert result.severity == "info"


def test_invalid_json_returns_low_confidence_fallback():
    svc = _make_service()
    msg = MagicMock()
    msg.content = [MagicMock(text="not valid json at all")]
    msg.model = "claude-sonnet-4-6"
    svc._client.messages.create.return_value = msg

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")

    assert result.confidence_score == Decimal("0.30")


def test_markdown_fenced_json_parsed():
    svc = _make_service()
    raw_with_fence = '```json\n{"insight_type":"pnl_summary","severity":"info","title":"T","summary":"S","explanation":"E","confidence_score":0.75}\n```'
    msg = MagicMock()
    msg.content = [MagicMock(text=raw_with_fence)]
    msg.model = "claude-sonnet-4-6"
    svc._client.messages.create.return_value = msg

    result = svc.generate("pnl_summary", {}, "2024-06-01", "2024-06-30")
    assert result.title == "T"
    assert result.confidence_score == Decimal("0.7500")


# ---------------------------------------------------------------------------
# INSIGHT_TYPES constant
# ---------------------------------------------------------------------------


def test_insight_types_count():
    assert len(INSIGHT_TYPES) == 7


def test_insight_types_no_duplicates():
    assert len(INSIGHT_TYPES) == len(set(INSIGHT_TYPES))


# ---------------------------------------------------------------------------
# InsightContextBuilder
# ---------------------------------------------------------------------------


def test_context_builder_pnl_summary_decimal_safe():
    from unittest.mock import MagicMock
    from decimal import Decimal

    report = MagicMock()
    report.line_items.net_revenue = Decimal("5000.00")
    report.line_items.cogs = Decimal("1500.00")
    report.line_items.cogs_pct = Decimal("30.00")
    report.line_items.gross_profit = Decimal("3500.00")
    report.line_items.labor_cost = Decimal("1000.00")
    report.line_items.labor_pct = Decimal("20.00")
    report.line_items.prime_cost = Decimal("2500.00")
    report.line_items.prime_cost_pct = Decimal("50.00")
    report.line_items.ebitda = Decimal("1000.00")
    report.line_items.ebitda_pct = Decimal("20.00")
    report.line_items.net_profit = Decimal("1000.00")
    report.order_count = 120
    report.expense_count = 15
    report.expense_breakdown = []

    ctx = InsightContextBuilder.pnl_summary(report)

    # All Decimal values must be serialized as strings
    import json
    serialized = json.dumps(ctx)  # must not raise
    assert "5000.00" in serialized


def test_context_builder_reconciliation_summary():
    from unittest.mock import MagicMock
    from decimal import Decimal

    flag1 = MagicMock()
    flag1.flag_type = "duplicate_invoice"
    flag1.severity = "high"
    flag1.is_resolved = False

    flag2 = MagicMock()
    flag2.flag_type = "uncategorized_expense"
    flag2.severity = "medium"
    flag2.is_resolved = True

    run = MagicMock()
    run.documents_checked = 10
    run.expenses_checked = 5
    run.toast_orders_checked = 20
    run.net_variance = Decimal("-50.00")

    ctx = InsightContextBuilder.reconciliation_summary([flag1, flag2], run)

    assert ctx["total_flags"] == 2
    assert ctx["unresolved_flags"] == 1
    assert ctx["flag_types"]["duplicate_invoice"] == 1
