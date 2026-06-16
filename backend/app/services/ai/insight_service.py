"""AI Insight generation service.

Calls Claude API to generate business insights from financial data.
AI MUST NOT modify source financial records — insights are read-only outputs.
Every insight includes confidence_score + explanation (required by CLAUDE.md).
"""
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import anthropic
import structlog

from app.core.config import settings
from app.db.models.ai_insight import INSIGHT_TYPES

logger = structlog.get_logger(__name__)

_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a restaurant financial analyst assistant.
Analyze the provided financial data and generate actionable business insights.

Rules:
- Never suggest modifying invoice amounts or sales records.
- Always ground insights in the numbers provided.
- Be specific: mention exact amounts, percentages, dates where relevant.
- Severity levels: info (FYI), warning (attention needed), critical (immediate action).

Respond ONLY with valid JSON matching this schema:
{
  "title": "short insight title (max 80 chars)",
  "summary": "1-2 sentence plain-English summary",
  "explanation": "detailed explanation with specific numbers and reasoning",
  "confidence_score": 0.00-1.00,
  "severity": "info|warning|critical",
  "insight_type": "<one of the allowed types>"
}"""


@dataclass
class InsightResult:
    insight_type: str
    severity: str
    title: str
    summary: str
    explanation: str
    confidence_score: Decimal
    model_id: str


class AIInsightService:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def generate(
        self,
        insight_type: str,
        context: dict,
        period_start: str,
        period_end: str,
    ) -> InsightResult:
        """Generate one insight synchronously.

        context — pre-assembled financial data dict; must not contain raw PII.
        Returns InsightResult; on any error returns a low-confidence fallback.
        """
        user_message = self._build_prompt(insight_type, context, period_start, period_end)

        try:
            response = self._client.messages.create(
                model=_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text
            return self._parse(raw, insight_type, response.model)
        except Exception as exc:
            logger.error("ai_insight_failed", insight_type=insight_type, error=str(exc))
            return InsightResult(
                insight_type=insight_type,
                severity="info",
                title="Insight generation failed",
                summary="Could not generate AI insight at this time.",
                explanation=str(exc),
                confidence_score=Decimal("0.00"),
                model_id=_MODEL,
            )

    def _build_prompt(
        self,
        insight_type: str,
        context: dict,
        period_start: str,
        period_end: str,
    ) -> str:
        lines = [
            f"Insight type requested: {insight_type}",
            f"Period: {period_start} to {period_end}",
            "",
            "Financial data:",
            json.dumps(context, indent=2, default=str),
        ]
        return "\n".join(lines)

    def _parse(self, raw: str, insight_type: str, model: str) -> InsightResult:
        try:
            # Strip markdown fences if present
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())

            parsed_type = data.get("insight_type", insight_type)
            if parsed_type not in INSIGHT_TYPES:
                parsed_type = insight_type

            severity = data.get("severity", "info")
            if severity not in ("info", "warning", "critical"):
                severity = "info"

            raw_confidence = float(data.get("confidence_score", 0.5))
            confidence = Decimal(str(max(0.0, min(1.0, raw_confidence)))).quantize(
                Decimal("0.0001")
            )

            return InsightResult(
                insight_type=parsed_type,
                severity=severity,
                title=str(data.get("title", "Untitled"))[:255],
                summary=str(data.get("summary", "")),
                explanation=str(data.get("explanation", "")),
                confidence_score=confidence,
                model_id=model,
            )
        except Exception as exc:
            logger.warning("ai_insight_parse_failed", error=str(exc), raw=raw[:200])
            return InsightResult(
                insight_type=insight_type,
                severity="info",
                title="Insight (parse error)",
                summary=raw[:500],
                explanation="Response could not be fully parsed.",
                confidence_score=Decimal("0.30"),
                model_id=model,
            )


class InsightContextBuilder:
    """Assembles context dict from DB data for each insight type.

    All amounts are converted to str (Decimal-safe for JSON serialization).
    Never includes raw personal data (employee names etc.) in context.
    """

    @staticmethod
    def pnl_summary(report) -> dict:
        li = report.line_items
        return {
            "net_revenue": str(li.net_revenue) if li.net_revenue else None,
            "cogs": str(li.cogs) if li.cogs else None,
            "cogs_pct": str(li.cogs_pct) if li.cogs_pct else None,
            "gross_profit": str(li.gross_profit) if li.gross_profit else None,
            "labor_cost": str(li.labor_cost) if li.labor_cost else None,
            "labor_pct": str(li.labor_pct) if li.labor_pct else None,
            "prime_cost": str(li.prime_cost) if li.prime_cost else None,
            "prime_cost_pct": str(li.prime_cost_pct) if li.prime_cost_pct else None,
            "ebitda": str(li.ebitda) if li.ebitda else None,
            "ebitda_pct": str(li.ebitda_pct) if li.ebitda_pct else None,
            "net_profit": str(li.net_profit) if li.net_profit else None,
            "order_count": report.order_count,
            "expense_count": report.expense_count,
            "expense_breakdown": [
                {"category": b.category, "total": str(b.total), "count": b.expense_count}
                for b in report.expense_breakdown
            ],
        }

    @staticmethod
    def category_analysis(report) -> dict:
        return {
            "expense_breakdown": [
                {"category": b.category, "total": str(b.total), "count": b.expense_count}
                for b in report.expense_breakdown
            ],
            "net_revenue": str(report.line_items.net_revenue) if report.line_items.net_revenue else None,
        }

    @staticmethod
    def reconciliation_summary(flags: list, run) -> dict:
        from collections import Counter
        type_counts = Counter(f.flag_type for f in flags)
        sev_counts = Counter(f.severity for f in flags)
        return {
            "total_flags": len(flags),
            "unresolved_flags": sum(1 for f in flags if not f.is_resolved),
            "flag_types": dict(type_counts),
            "severities": dict(sev_counts),
            "documents_checked": run.documents_checked,
            "expenses_checked": run.expenses_checked,
            "toast_orders_checked": run.toast_orders_checked,
            "net_variance": str(run.net_variance) if run.net_variance else None,
        }

    @staticmethod
    def expense_anomaly(flagged_expenses: list) -> dict:
        return {
            "anomalous_expenses": [
                {
                    "vendor": e.vendor_name,
                    "amount": str(e.amount),
                    "category": e.category,
                }
                for e in flagged_expenses[:20]  # cap at 20 to keep context small
            ],
            "count": len(flagged_expenses),
        }

    @staticmethod
    def vendor_analysis(category_totals: dict, period_days: int) -> dict:
        return {
            "period_days": period_days,
            "vendor_totals": {
                vendor: str(total) for vendor, total in list(category_totals.items())[:30]
            },
        }
