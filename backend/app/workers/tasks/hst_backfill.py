"""Backfill HST/GST tax_amount on already-extracted documents + expenses.

Existing invoices/receipts were OCR'd before tax_amount was captured. Rather
than re-run full OCR (costly), re-read the stored extracted_text with a cheap
Claude haiku call and pull just the tax line. Idempotent: only touches rows
where tax_amount is still NULL.
"""
import asyncio
import json
import uuid
from decimal import Decimal, InvalidOperation

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

_TAX_PROMPT = (
    "Extract ONLY the sales tax total (HST/GST/QST/PST in Canada, or VAT/sales tax) "
    "from this invoice/receipt text. Sum multiple tax lines. Respond with ONLY a JSON "
    'object: {"tax_amount": number or null}. Plain number, no symbols. null if no tax '
    "shown. This is the tax charged, NOT the grand total.\n\nDOCUMENT TEXT:\n"
)


def _parse(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


async def _extract_tax(text: str) -> Decimal | None:
    import anthropic

    from app.core.config import settings

    if not text or len(text) < 20:
        return None
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": _TAX_PROMPT + text[:6000]}],
    )
    raw = msg.content[0].text.strip()  # type: ignore[union-attr]
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    try:
        return _parse(json.loads(raw).get("tax_amount"))
    except (json.JSONDecodeError, AttributeError):
        return None


async def _run(tenant_id_str: str, limit: int) -> dict:
    from sqlalchemy import select

    from app.db.models.document import Document, OCRResult
    from app.db.models.expense import Expense
    from app.db.session import AsyncSessionLocal

    tenant_id = uuid.UUID(tenant_id_str)
    updated = 0
    scanned = 0

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Document.id, OCRResult.extracted_text)
                .join(OCRResult, OCRResult.document_id == Document.id)
                .where(
                    Document.tenant_id == tenant_id,
                    Document.status == "extracted",
                    Document.tax_amount.is_(None),
                    Document.document_type.in_(["invoice", "receipt"]),
                )
                .limit(limit)
            )
        ).all()

        for doc_id, text in rows:
            scanned += 1
            try:
                tax = await _extract_tax(text or "")
            except Exception as exc:  # noqa: BLE001
                logger.warning("hst_backfill_extract_failed", document_id=str(doc_id), error=str(exc))
                continue
            # No tax line found → record 0 (most food invoices are zero-rated), so
            # the doc is marked scanned and a later backfill won't re-bill haiku on it.
            if tax is None:
                tax = Decimal("0")
            doc = await db.get(Document, doc_id)
            if doc is not None:
                doc.tax_amount = tax
            exp = (
                await db.execute(select(Expense).where(Expense.document_id == doc_id))
            ).scalars().first()
            if exp is not None and exp.tax_amount is None:
                exp.tax_amount = tax
            updated += 1
            if updated % 25 == 0:
                await db.commit()
        await db.commit()

    logger.info("hst_backfill_done", tenant_id=tenant_id_str, scanned=scanned, updated=updated)
    return {"status": "ok", "scanned": scanned, "updated": updated}


@celery_app.task(name="app.workers.tasks.hst_backfill.backfill_hst", queue="ocr")
def backfill_hst(tenant_id: str, limit: int = 500) -> dict:
    return asyncio.run(_run(tenant_id, limit))
