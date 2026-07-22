"""OCR adapter: markitdown text extraction + a cheap Claude text-structuring pass.

Native-text PDFs (most invoices/receipts) carry a real text layer. markitdown
pulls that to markdown with no LLM cost, then a Claude haiku call structures the
text into fields — far cheaper than sending page images to Claude Vision
(~200-400 tokens vs ~1-2k/page). Scanned/image-only PDFs yield no text; those
raise so AutoOCRAdapter falls back to Google Document AI / Claude Vision.
"""
import io
import json
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Optional

import structlog

from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult

logger = structlog.get_logger(__name__)

# Below this many non-whitespace chars the PDF has no usable text layer
# (scanned image) — bail so a real OCR engine handles it.
_MIN_TEXT_CHARS = 40

_STRUCT_PROMPT = """You are a financial document parser. Below is the extracted TEXT of an invoice/receipt/statement (already OCR'd to markdown). Extract structured data.

Respond with ONLY a valid JSON object — no markdown fences, no preamble:
{
  "vendor_name": "string or null",
  "document_date": "YYYY-MM-DD or null",
  "total_amount": number or null,
  "tax_amount": number or null,
  "currency_code": "3-letter code, default CAD",
  "line_items": [{"description": "string", "amount": number or null, "quantity": number or null, "unit_price": number or null}]
}

Rules:
- amounts as plain numbers (no symbols/commas)
- tax_amount: the sales-tax total (HST/GST/QST/PST/VAT). Sum multiple tax lines. null if none. NOT the grand total.
- currency_code: CAD if Canadian vendor, USD if US, else infer
- line_items: every line visible

DOCUMENT TEXT:
"""


def _dec(v) -> Optional[Decimal]:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


class MarkItDownAdapter(OCRAdapter):
    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        start = time.time()
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert_stream(io.BytesIO(file_bytes))
        text = (result.text_content or "").strip()

        if len(re.sub(r"\s", "", text)) < _MIN_TEXT_CHARS:
            raise ValueError("markitdown: no usable text layer (scanned/image PDF)")

        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8000,
            messages=[{"role": "user", "content": _STRUCT_PROMPT + text[:20000]}],
        )
        raw = msg.content[0].text.strip()  # type: ignore[union-attr]
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            raw = fence.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("markitdown_struct_json_failed", tail=raw[-160:])
            raise ValueError("markitdown: structuring returned non-JSON")

        line_items: list[OCRLineItem] = []
        for li in data.get("line_items") or []:
            if not isinstance(li, dict):
                continue
            desc = (li.get("description") or "").strip()
            amt = _dec(li.get("amount"))
            if not desc and amt is None:
                continue
            line_items.append(
                OCRLineItem(
                    description=desc,
                    amount=amt or Decimal("0"),
                    quantity=_dec(li.get("quantity")),
                    unit_price=_dec(li.get("unit_price")),
                    confidence_score=Decimal("0.85"),
                )
            )

        return OCRResult(
            provider="markitdown_text",
            extracted_text=text,
            raw_response={"provider": "markitdown_text", "chars": len(text)},
            vendor_name=(data.get("vendor_name") or None),
            total_amount=_dec(data.get("total_amount")),
            tax_amount=_dec(data.get("tax_amount")),
            document_date=data.get("document_date") or None,
            currency_code=(data.get("currency_code") or "CAD").strip().upper()[:3],
            line_items=line_items,
            confidence_score=Decimal("0.85"),
            page_count=1,
            processing_time_ms=int((time.time() - start) * 1000),
        )
