"""Free, fully-local OCR adapter using Tesseract.

Zero API cost — no Anthropic / Google credits burned. Extracts raw text only;
returns no structured invoice fields (vendor/total/line_items). Downstream
bank-statement parsing already falls back to text parsing, so this adapter is a
good fit for bank statements. For structured invoices, Google Document AI or
Claude Vision give far better field extraction.

Requires system packages: `tesseract-ocr` and `poppler-utils` (for PDF→image),
plus Python packages `pytesseract` and `pdf2image` / `Pillow`.
"""
import time
from decimal import Decimal

from app.services.ocr.base import OCRAdapter, OCRResult


class TesseractAdapter(OCRAdapter):
    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        start = time.monotonic()
        text, pages = self._extract_text(file_bytes, mime_type)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        return OCRResult(
            provider="tesseract",
            extracted_text=text,
            raw_response={"engine": "tesseract", "mime_type": mime_type},
            vendor_name=None,
            total_amount=None,
            document_date=None,
            currency_code="CAD",
            line_items=[],
            confidence_score=Decimal("0.50"),
            page_count=pages,
            processing_time_ms=elapsed_ms,
        )

    def _extract_text(self, file_bytes: bytes, mime_type: str) -> tuple[str, int]:
        import io

        import pytesseract
        from PIL import Image

        if mime_type == "application/pdf":
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(file_bytes)
            texts = [pytesseract.image_to_string(img) for img in images]
            return "\n".join(texts), len(images)

        img = Image.open(io.BytesIO(file_bytes))
        return pytesseract.image_to_string(img), 1
