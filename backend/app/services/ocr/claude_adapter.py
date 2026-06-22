"""
OCR adapter using Claude Vision API.
Converts PDFs to images via PyMuPDF, sends to Claude with structured extraction prompt.
Falls back to text extraction for image mime types directly.
"""
import base64
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

import anthropic
import structlog

from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult

logger = structlog.get_logger(__name__)

_EXTRACTION_PROMPT = """You are a financial document parser. Extract structured data from this invoice/receipt/statement.
You are given every page of the document, in order, as separate images. Treat them as one document.

Respond with ONLY a valid JSON object — no markdown fences, no preamble:
{
  "vendor_name": "string or null",
  "document_date": "YYYY-MM-DD or null",
  "total_amount": number or null,
  "currency_code": "3-letter code, default CAD",
  "line_items": [
    {
      "description": "string",
      "amount": number or null,
      "quantity": number or null,
      "unit_price": number or null
    }
  ],
  "extracted_text": "full raw text visible across ALL pages, concatenated in page order"
}

Rules:
- amounts as plain numbers (no currency symbols, no commas)
- date as YYYY-MM-DD
- currency_code: CAD if Canadian vendor, USD if US, else infer from symbols
- line_items: include EVERY line item / transaction visible across ALL pages, not just the first page. For bank
  or credit card statements this means every individual transaction line, not just the summary totals.
- extracted_text: all text you can read from every page, concatenated"""


# Hard cap on pages sent to Claude per document — bank statements run 3-8
# pages; this leaves headroom while keeping a single API call's image count
# (and cost) bounded against a pathological 200-page upload.
_MAX_OCR_PAGES = 20


def _pdf_to_image_bytes_all_pages(file_bytes: bytes) -> tuple[list[bytes], int]:
    """Convert every page of a PDF to PNG bytes using PyMuPDF.

    Returns (images, total_page_count). Multi-page documents (bank statements,
    multi-line invoices) lose every transaction past page 1 if only the first
    page is rendered — this previously hardcoded doc[0] and silently dropped
    pages 2+.
    """
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    total_pages = len(doc)
    images = []
    for i in range(min(total_pages, _MAX_OCR_PAGES)):
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR quality
        pix = doc[i].get_pixmap(matrix=mat)
        images.append(pix.tobytes("png"))
    return images, total_pages


_BANK_PAGE_PROMPT = """This is ONE page of a bank or credit-card statement. List EVERY money-OUT
transaction visible on THIS page only.

Money-OUT = chequing 'amounts debited' column (pre-authorized payments, withdrawals,
purchases, fees, interest paid) OR every purchase/charge line on a credit-card statement.

EXCLUDE: deposits, direct deposits, credits, refunds, interest earned, transfers in,
opening/closing/previous/new balance lines, minimum-payment lines, and payment lines that
REDUCE a credit-card balance (TRSF FROM, PAYMENT - THANK YOU).

Respond with ONLY a JSON array, no markdown:
[{"description": "vendor/text as shown", "amount": 123.45, "date": "YYYY-MM-DD or MM/DD or null"}]
- amount: positive number, no symbols/commas
- include EVERY qualifying line on this page, even repeats of the same vendor with different amounts
- return [] if none on this page"""


async def extract_bank_transactions_per_page(
    file_bytes: bytes, mime_type: str, statement_year: int | None = None
) -> list[dict]:
    """Extract bank debit/charge transactions ONE PAGE AT A TIME.

    A single whole-document call truncates its JSON on dense multi-page statements
    (40+ transactions) and silently drops most rows — the recurring 'P&L is
    incomplete / inconsistent' bug. Parsing each page in its own bounded call keeps
    every output small and complete, then we accumulate. Returns a list of
    {description, amount (positive float), date (str|None)}."""
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    if mime_type == "application/pdf" or mime_type.endswith("/pdf"):
        page_images, _ = _pdf_to_image_bytes_all_pages(file_bytes)
        media_type = "image/png"
    else:
        page_images, media_type = [file_bytes], mime_type

    out: list[dict] = []
    for idx, img in enumerate(page_images):
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(img).decode(),
                },
            },
            {"type": "text", "text": _BANK_PAGE_PROMPT},
        ]
        try:
            msg = client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=8000,
                messages=[{"role": "user", "content": content}],
            )
            raw = msg.content[0].text.strip()  # type: ignore[union-attr]
            fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if fence:
                raw = fence.group(1).strip()
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1:
                continue
            rows = json.loads(raw[start : end + 1])
        except Exception as exc:
            logger.warning("bank_page_parse_failed", page=idx, error=str(exc))
            continue

        for r in rows if isinstance(rows, list) else []:
            if not isinstance(r, dict):
                continue
            desc = str(r.get("description", "")).strip()
            amt = _parse_decimal(r.get("amount"))
            if not desc or amt is None or amt <= 0:
                continue
            out.append({
                "description": desc,
                "amount": amt,
                "date": _normalize_date(r.get("date"), statement_year),
            })

    logger.info("bank_per_page_extracted", pages=len(page_images), transactions=len(out))
    return out


def _normalize_date(val, statement_year: int | None) -> Optional[str]:
    """Accept YYYY-MM-DD or MM/DD (year inferred from statement) → YYYY-MM-DD."""
    if not val:
        return None
    s = str(val).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", s)
    if m and statement_year:
        return f"{statement_year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _parse_decimal(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except InvalidOperation:
        return None


class ClaudeVisionAdapter(OCRAdapter):
    """
    OCR adapter using Claude Vision (claude-sonnet-4-6).
    Sends invoice as image to Claude, extracts structured fields via JSON prompt.
    Requires ANTHROPIC_API_KEY in settings.
    """

    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        # Convert PDF to images (one per page) for vision
        if mime_type == "application/pdf" or mime_type.endswith("/pdf"):
            page_images, total_pages = _pdf_to_image_bytes_all_pages(file_bytes)
            image_media_type = "image/png"
        else:
            page_images, total_pages = [file_bytes], 1
            image_media_type = mime_type

        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": base64.standard_b64encode(img).decode(),
                },
            }
            for img in page_images
        ]
        content.append({"type": "text", "text": _EXTRACTION_PROMPT})

        message = client.messages.create(
            model=settings.CLAUDE_MODEL,
            # Multi-page bank/credit-card statements can list 100+ transactions —
            # 4096 truncated mid-JSON and silently produced zero line items.
            max_tokens=16000,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = message.content[0].text  # type: ignore[union-attr]
        raw_response = {"provider": "claude_vision", "model": settings.CLAUDE_MODEL, "raw": raw_text[:2000]}

        # Strip any accidental markdown fences
        cleaned = raw_text.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
        if fence:
            cleaned = fence.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error(
                "ocr_json_parse_failed",
                stop_reason=getattr(message, "stop_reason", None),
                response_length=len(raw_text),
                response_tail=raw_text[-200:],
            )
            data = {}

        vendor_name: Optional[str] = data.get("vendor_name")
        document_date: Optional[str] = data.get("document_date")
        total_amount = _parse_decimal(data.get("total_amount"))
        currency_code = (data.get("currency_code") or "CAD").strip().upper()[:3]
        extracted_text = data.get("extracted_text") or ""

        line_items: list[OCRLineItem] = []
        _seen_items: set[tuple] = set()
        for li in data.get("line_items") or []:
            if not isinstance(li, dict):
                continue
            desc = li.get("description") or ""
            amount = _parse_decimal(li.get("amount"))
            if not desc and amount is None:
                continue
            qty = _parse_decimal(li.get("quantity"))
            unit_price = _parse_decimal(li.get("unit_price"))
            # Deduplicate — Claude Vision sometimes repeats identical line items
            dedup_key = (desc.strip().lower(), str(qty), str(unit_price))
            if dedup_key in _seen_items:
                continue
            _seen_items.add(dedup_key)
            line_items.append(
                OCRLineItem(
                    description=desc,
                    amount=amount or Decimal("0"),
                    quantity=qty,
                    unit_price=unit_price,
                    confidence_score=Decimal("0.90"),
                )
            )

        return OCRResult(
            provider="claude_vision",
            extracted_text=extracted_text,
            raw_response=raw_response,
            vendor_name=vendor_name or None,
            total_amount=total_amount,
            document_date=document_date,
            currency_code=currency_code,
            line_items=line_items,
            confidence_score=Decimal("0.90"),
            page_count=total_pages,
            processing_time_ms=0,
        )
