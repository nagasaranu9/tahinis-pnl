"""AI-powered expense categorization using Claude API.

AI may suggest categories and explain reasoning.
AI must never modify source financial records.
Every AI output includes confidence_score and explanation.
"""
import uuid
from decimal import Decimal

import anthropic
import structlog

from app.core.config import settings
from app.db.models.expense import EXPENSE_CATEGORIES

logger = structlog.get_logger(__name__)

_CATEGORIES_LIST = "\n".join(f"- {c}" for c in sorted(EXPENSE_CATEGORIES))

_SYSTEM_PROMPT = f"""You are a restaurant financial expert. Categorize expenses into exactly one of these categories:

{_CATEGORIES_LIST}

Respond with a JSON object containing:
- "category": exactly one category from the list above
- "confidence": float 0.0–1.0 (your confidence in this categorization)
- "explanation": one concise sentence explaining the categorization

Respond ONLY with valid JSON. No prose before or after."""


class CategorizationResult:
    def __init__(self, category: str, confidence: Decimal, explanation: str) -> None:
        self.category = category
        self.confidence = confidence
        self.explanation = explanation


# Deterministic vendor/keyword -> category map. Matched against the vendor name
# and line-item text BEFORE any AI call, so common Canadian restaurant bank
# transactions categorize for free (no Anthropic credits) and never land in
# "Uncategorized". Order matters: first substring hit wins. Keep keywords lower.
_KEYWORD_CATEGORY_MAP: list[tuple[tuple[str, ...], str]] = [
    # Payroll / labor
    (("pushoperation", "pushops", "payroll", "wage", "adp ", "ceridian", "wagepoint"), "Payroll"),
    # Utilities (telecom + hydro/gas/water)
    (("telus", "rogers", "bell ", "bell canada", "fido", "koodo", "videotron",
      "hydro", "enbridge", "fortis", "epcor", "toronto hydro", "alectra",
      "utilit", "gas company", "water", "energy"), "Utilities"),
    # Rent / lease of premises
    (("rent", "landlord", "lease", "property mgmt", "realty", "leasing"), "Rent"),
    # Insurance
    (("insurance", "intact", "aviva", "wawanesa", "sonnet", "co-operators",
      "assurance", "ins ", "ins.", "gms"), "Insurance"),
    # Software / SaaS
    (("toast", "quickbooks", "intuit", "shopify", "square ", "stripe", "google ",
      "microsoft", "adobe", "zoom", "slack", "godaddy", "mailchimp", "ubereats tech",
      "software", "saas", "subscription", "app store", "aws", "amazon web"), "Software"),
    # Marketing / ads
    (("google ads", "facebook", "meta platforms", "instagram", "advertis",
      "marketing", "yelp", "groupon", "promo"), "Marketing"),
    # Royalties / franchise fees
    (("royalt", "franchise"), "Royalties"),
    # Repairs & maintenance
    (("repair", "hvac", "plumb", "electric", "maintenance", "handyman",
      "appliance", "refrigerat"), "Repairs"),
    # Cleaning / sanitation / linen
    (("cleaning", "janitor", "sanitat", "ecolab", "linen", "pest control", "waste"), "Cleaning"),
    # Packaging / disposables
    (("packaging", "container", "disposable", "uline", "dart ", "cutlery", "napkin"), "Packaging"),
    # Beverage suppliers
    (("coca-cola", "coca cola", "pepsi", "beverage", "lcbo", "liquor", "brewery",
      "coffee", "beer", "wine"), "Beverage Cost"),
    # Food suppliers / distributors
    (("sysco", "gordon food", "gfs", "costco", "restaurant depot", "produce",
      "meat", "bakery", "food service", "wholesale", "distribut", "grocery",
      "farm", "dairy", "halal", "fresh"), "Food Cost"),
    # Professional services / bank & financing costs
    (("interest paid", "interest charge", "bank fee", "service charge", "accounting",
      "accountant", "lawyer", "legal", "consult", "professional", "audit", "notary",
      "loan", "financing", "amex annual", "card fee"), "Professional Services"),
]


def keyword_category(vendor_name: str | None, line_item_descriptions: list[str] | None) -> str | None:
    """Return a deterministic category if vendor/line-items match a known keyword.

    No network, no AI cost. Returns None when nothing matches (caller falls back
    to the AI categorizer)."""
    haystack = " ".join(
        filter(None, [vendor_name or "", " ".join(line_item_descriptions or [])])
    ).lower()
    if not haystack.strip():
        return None
    for keywords, category in _KEYWORD_CATEGORY_MAP:
        if any(k in haystack for k in keywords):
            return category
    return None


class CategorizationService:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def categorize(
        self,
        vendor_name: str | None,
        amount: Decimal | None,
        currency_code: str,
        document_type: str | None = None,
        line_item_descriptions: list[str] | None = None,
    ) -> CategorizationResult:
        # 1. Deterministic keyword match first — free, instant, no AI credits.
        kw = keyword_category(vendor_name, line_item_descriptions)
        if kw is not None:
            return CategorizationResult(
                category=kw,
                confidence=Decimal("0.90"),
                explanation=f"Matched known vendor/keyword to {kw}.",
            )

        # 2. Fall back to AI only when no keyword matched.
        user_message = self._build_user_message(
            vendor_name, amount, currency_code, document_type, line_item_descriptions
        )

        try:
            message = self._client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=256,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            return self._parse_response(message.content[0].text)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("ai_categorization_failed", error=str(exc))
            return CategorizationResult(
                category="Miscellaneous",
                confidence=Decimal("0.00"),
                explanation="AI categorization failed; defaulted to Miscellaneous.",
            )

    def _build_user_message(
        self,
        vendor_name: str | None,
        amount: Decimal | None,
        currency_code: str,
        document_type: str | None,
        line_item_descriptions: list[str] | None,
    ) -> str:
        parts = []
        if vendor_name:
            parts.append(f"Vendor: {vendor_name}")
        if amount is not None:
            parts.append(f"Amount: {amount} {currency_code}")
        if document_type:
            parts.append(f"Document type: {document_type}")
        if line_item_descriptions:
            descriptions = "; ".join(line_item_descriptions[:10])
            parts.append(f"Line items: {descriptions}")
        return "\n".join(parts) if parts else "No vendor or amount information available."

    def _parse_response(self, text: str) -> CategorizationResult:
        import json
        import re

        try:
            cleaned = text.strip()
            # Strip markdown code fences if present
            fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
            if fence_match:
                cleaned = fence_match.group(1).strip()
            data = json.loads(cleaned)
            category = data.get("category", "Miscellaneous")
            if category not in EXPENSE_CATEGORIES:
                category = "Miscellaneous"
            confidence = Decimal(str(data.get("confidence", 0.5))).quantize(Decimal("0.0001"))
            explanation = str(data.get("explanation", ""))
            return CategorizationResult(category=category, confidence=confidence, explanation=explanation)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("ai_response_parse_failed", error=str(exc), raw=text[:200])
            return CategorizationResult(
                category="Miscellaneous",
                confidence=Decimal("0.00"),
                explanation="Could not parse AI response; defaulted to Miscellaneous.",
            )
