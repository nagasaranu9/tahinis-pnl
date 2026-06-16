from decimal import Decimal, InvalidOperation
from typing import Optional

from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult


class GoogleDocumentAIAdapter(OCRAdapter):
    """
    OCR adapter using Google Document AI Invoice Parser.
    Requires GOOGLE_DOC_AI_PROJECT_ID, GOOGLE_DOC_AI_LOCATION, GOOGLE_DOC_AI_PROCESSOR_ID.
    Authenticates via GOOGLE_APPLICATION_CREDENTIALS (service account JSON).
    """

    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai

        client = documentai.DocumentProcessorServiceClient(
            client_options=ClientOptions(
                api_endpoint=f"{settings.GOOGLE_DOC_AI_LOCATION}-documentai.googleapis.com"
            )
        )
        processor_name = client.processor_path(
            settings.GOOGLE_DOC_AI_PROJECT_ID,
            settings.GOOGLE_DOC_AI_LOCATION,
            settings.GOOGLE_DOC_AI_PROCESSOR_ID,
        )

        raw_document = documentai.RawDocument(content=file_bytes, mime_type=mime_type)
        request = documentai.ProcessRequest(name=processor_name, raw_document=raw_document)
        response = client.process_document(request=request)
        document = response.document

        extracted_text = document.text or ""
        raw_response = {"text": extracted_text[:2000], "mime_type": mime_type}

        vendor_name: Optional[str] = None
        total_amount: Optional[Decimal] = None
        document_date: Optional[str] = None
        currency_code = "CAD"
        line_items: list[OCRLineItem] = []
        confidence_scores: list[float] = []

        for entity in document.entities:
            t = entity.type_
            val = entity.mention_text or ""
            conf = entity.confidence or 0.0
            confidence_scores.append(conf)

            if t == "supplier_name" and not vendor_name:
                vendor_name = val.strip()
            elif t == "invoice_date" and not document_date:
                document_date = _parse_date(val)
            elif t == "total_amount" and not total_amount:
                total_amount = _parse_money(val)
            elif t == "currency" and val:
                currency_code = val.strip().upper()[:3]
            elif t == "line_item":
                li = _parse_line_item(entity, conf)
                if li:
                    line_items.append(li)

        overall_confidence = (
            Decimal(str(round(sum(confidence_scores) / len(confidence_scores), 4)))
            if confidence_scores
            else Decimal("0.00")
        )

        return OCRResult(
            provider="google_document_ai",
            extracted_text=extracted_text,
            raw_response=raw_response,
            vendor_name=vendor_name,
            total_amount=total_amount,
            document_date=document_date,
            currency_code=currency_code,
            line_items=line_items,
            confidence_score=overall_confidence,
            page_count=len(document.pages),
        )


def _parse_money(text: str) -> Optional[Decimal]:
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(text: str) -> Optional[str]:
    if not text:
        return None
    import re
    from datetime import datetime

    text = text.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m:
        return m.group(1)
    return None


def _parse_line_item(entity, confidence: float) -> Optional[OCRLineItem]:
    desc: Optional[str] = None
    amount: Optional[Decimal] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None

    for prop in entity.properties:
        t = prop.type_
        val = prop.mention_text or ""
        if t == "line_item/description":
            desc = val.strip()
        elif t == "line_item/amount":
            amount = _parse_money(val)
        elif t == "line_item/quantity":
            try:
                quantity = Decimal(val.replace(",", "").strip())
            except InvalidOperation:
                pass
        elif t == "line_item/unit_price":
            unit_price = _parse_money(val)

    if not desc and amount is None:
        return None

    return OCRLineItem(
        description=desc or "",
        amount=amount,
        quantity=quantity,
        unit_price=unit_price,
        confidence_score=Decimal(str(round(confidence, 4))),
    )
