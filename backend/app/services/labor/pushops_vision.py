"""
PushOperations payroll OCR import (image / PDF path).

Lower-tier PushOps cannot export CSV, so the operator uploads a screenshot or
PDF of the "Payroll Summary by Period" report instead. We read it with Claude
Vision, but the **money math stays in Python**: the model only transcribes the
raw table cells (gross, employer CPP/EI, WCB) and we compute the fully-burdened
labor cost ourselves — identical formula to the CSV path
(`pushops_import._parse_summary`) so both upload routes produce the same number.

This keeps the authoritative cost calculation deterministic and out of the
model's hands (CLAUDE.md: never trust AI output without validation).
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import anthropic
import structlog

from app.core.config import settings
from app.services.labor.pushops_import import LaborLineItem, PushOpsParseError

logger = structlog.get_logger(__name__)

_MAX_BYTES = 5 * 1024 * 1024

_IMAGE_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "webp": "image/webp",
    "gif": "image/gif",
}

_PROMPT = """You are a payroll-report transcriber. The image(s) are a PushOperations \
"Payroll Summary by Period" report (one row per pay period, or per employee).

Transcribe EVERY data row. Do NOT compute totals and do NOT include any \
"Total"/"Grand Total" summary row. Read numbers exactly as shown.

Respond with ONLY a valid JSON object — no markdown fences, no preamble:
{
  "currency_code": "3-letter code, default CAD",
  "confidence": number between 0 and 1 (your overall transcription confidence),
  "rows": [
    {
      "employee": "string or null (null for period-summary rows)",
      "pay_date": "YYYY-MM-DD",
      "total_gross": number or null,
      "employer_cpp": number or null,
      "employer_ei": number or null,
      "wcb": number or null,
      "fully_burdened": number or null
    }
  ]
}

Rules:
- numbers as plain values: no $, no commas, no parentheses (use a leading minus for negatives)
- pay_date as YYYY-MM-DD; if only a period range is shown, use the period END date
- employer_cpp / employer_ei are the EMPLOYER-side amounts only (ignore the employee deduction columns of the same name)
- wcb = WCB / workers' compensation employer cost if present, else null
- fully_burdened: only fill this if the report shows a single explicit "total cost to employer" column; otherwise null
- never invent values; use null when a cell is blank or unreadable"""


@dataclass(frozen=True)
class VisionExtraction:
    items: list[LaborLineItem]
    currency_code: str
    confidence: Decimal


def is_image_or_pdf(mime_type: str | None, filename: str | None) -> bool:
    m = (mime_type or "").lower()
    if m.startswith("image/") or m == "application/pdf" or m.endswith("/pdf"):
        return True
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return ext in (*_IMAGE_MIME.keys(), "pdf")


def _media_type(mime_type: str | None, filename: str | None) -> str:
    m = (mime_type or "").lower()
    if m.startswith("image/"):
        return m
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    return _IMAGE_MIME.get(ext, "image/png")


def _to_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _parse_pay_date(raw, fallback: date | None) -> date | None:
    if raw:
        s = str(raw).strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return fallback


def extract_pushops_image(
    file_bytes: bytes,
    mime_type: str | None,
    filename: str | None = None,
    fallback_pay_date: date | None = None,
) -> VisionExtraction:
    """Read a payroll screenshot/PDF and return fully-burdened labor line items.

    Raises PushOpsParseError on empty/oversized input, no API key, or when no
    usable rows can be read.
    """
    if not file_bytes:
        raise PushOpsParseError("Empty file")
    if len(file_bytes) > _MAX_BYTES:
        raise PushOpsParseError("File too large (max 5 MB)")
    if not settings.ANTHROPIC_API_KEY:
        raise PushOpsParseError(
            "Image upload needs OCR, which requires ANTHROPIC_API_KEY. "
            "Upload a CSV export instead, or configure the key."
        )

    m = (mime_type or "").lower()
    if m == "application/pdf" or m.endswith("/pdf") or (filename or "").lower().endswith(".pdf"):
        from app.services.ocr.claude_adapter import _pdf_to_image_bytes_all_pages

        page_images, _ = _pdf_to_image_bytes_all_pages(file_bytes)
        media_type = "image/png"
    else:
        page_images = [file_bytes]
        media_type = _media_type(mime_type, filename)

    content: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(img).decode(),
            },
        }
        for img in page_images
    ]
    content.append({"type": "text", "text": _PROMPT})

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = message.content[0].text  # type: ignore[union-attr]
    cleaned = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("pushops_ocr_json_failed", tail=raw_text[-200:])
        raise PushOpsParseError("Could not read the payroll image. Try a clearer photo or a CSV.") from exc

    currency = (data.get("currency_code") or "CAD").strip().upper()[:3] or "CAD"
    confidence = _to_decimal(data.get("confidence")) or Decimal("0")

    items: list[LaborLineItem] = []
    for row in data.get("rows") or []:
        if not isinstance(row, dict):
            continue
        employee = row.get("employee")
        employee = str(employee).strip() or None if employee else None
        if employee and employee.lower() in ("total", "totals", "grand total"):
            continue

        pay_date = _parse_pay_date(row.get("pay_date"), fallback_pay_date)
        if pay_date is None:
            continue

        # Fully-burdened cost: prefer computing from raw cells (single source of
        # truth with the CSV path); fall back to an explicit total column.
        gross = _to_decimal(row.get("total_gross"))
        cpp = _to_decimal(row.get("employer_cpp")) or Decimal("0")
        ei = _to_decimal(row.get("employer_ei")) or Decimal("0")
        wcb = _to_decimal(row.get("wcb")) or Decimal("0")
        if gross is not None:
            amount = gross + cpp + ei + wcb
        else:
            amount = _to_decimal(row.get("fully_burdened")) or Decimal("0")
        if amount <= 0:
            continue

        items.append(
            LaborLineItem(
                employee=employee,
                pay_date=pay_date,
                amount=amount,
                location_hint=None,
            )
        )

    if not items:
        raise PushOpsParseError("No payroll rows could be read from the image")

    logger.info("pushops_ocr_extracted", rows=len(items), confidence=str(confidence))
    return VisionExtraction(items=items, currency_code=currency, confidence=confidence)
