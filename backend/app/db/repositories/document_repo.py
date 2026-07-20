from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.document import Document, ExtractedLineItem, OCRResult

# Words too generic to prove or disprove vendor identity on their own —
# stripped before token-overlap comparison in find_content_duplicate.
_VENDOR_NOISE = frozenset(
    {"corp", "corp.", "inc", "inc.", "ltd", "ltd.", "llc", "co", "co.", "the", "a", "of"}
)

# Matches "INV-021842", "Invoice_INV019362", "Invoice_231034_from_..." — the
# invoice number a vendor assigns is unique per invoice, so two files with the
# same vendor+date+amount but different embedded invoice numbers are two real
# invoices, not a re-upload of the same one (a vendor issuing several
# same-total invoices to the same customer on the same day is common — daily
# delivery batches, credit memos — not a coincidence to be collapsed).
_INVOICE_NUMBER_RE = re.compile(r"(?:INV|Invoice)[_\-]?0*(\d{4,})", re.IGNORECASE)


def _vendor_tokens(name: str | None) -> frozenset[str]:
    if not name:
        return frozenset()
    raw = name.lower().replace(".", " ").replace(",", " ").split()
    return frozenset(t for t in raw if t and t not in _VENDOR_NOISE and len(t) > 1)


def _extract_invoice_number(filename: str | None) -> str | None:
    if not filename:
        return None
    m = _INVOICE_NUMBER_RE.search(filename)
    return m.group(1).lstrip("0") or None if m else None


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        tenant_id: uuid.UUID,
        created_by: uuid.UUID,
        *,
        original_filename: str,
        storage_path: str,
        mime_type: str,
        file_size_bytes: int,
        checksum_sha256: str,
        source: str = "manual_upload",
        source_id: str | None = None,
        location_id: uuid.UUID | None = None,
    ) -> Document:
        doc = Document(
            tenant_id=tenant_id,
            created_by=created_by,
            original_filename=original_filename,
            storage_path=storage_path,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            checksum_sha256=checksum_sha256,
            source=source,
            source_id=source_id,
            location_id=location_id,
            status="pending",
        )
        self._db.add(doc)
        await self._db.flush()
        return doc

    async def get(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> Document:
        result = await self._db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
            )
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            raise NotFoundError("Document not found")
        return doc

    async def list(
        self,
        tenant_id: uuid.UUID,
        *,
        status: str | None = None,
        document_type: str | None = None,
        location_id: uuid.UUID | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        query = select(Document).where(Document.tenant_id == tenant_id)
        count_query = select(Document).where(Document.tenant_id == tenant_id)

        if status:
            query = query.where(Document.status == status)
            count_query = count_query.where(Document.status == status)
        if document_type:
            query = query.where(Document.document_type == document_type)
            count_query = count_query.where(Document.document_type == document_type)
        if location_id:
            query = query.where(Document.location_id == location_id)
            count_query = count_query.where(Document.location_id == location_id)

        query = query.order_by(Document.created_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await self._db.execute(query)
        docs = list(result.scalars().all())

        from sqlalchemy import func
        count_result = await self._db.execute(
            select(func.count()).select_from(count_query.subquery())
        )
        total = count_result.scalar_one()
        return docs, total

    async def update_status(
        self,
        document_id: uuid.UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        values: dict = {"status": status}
        if error_message is not None:
            values["error_message"] = error_message
        await self._db.execute(update(Document).where(Document.id == document_id).values(**values))

    async def update_extracted_data(
        self,
        document_id: uuid.UUID,
        *,
        vendor_name: str | None,
        document_date: datetime | None,
        total_amount: Decimal | None,
        currency_code: str,
        document_type: str,
        tax_amount: Decimal | None = None,
    ) -> None:
        await self._db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                vendor_name=vendor_name,
                document_date=document_date,
                total_amount=total_amount,
                tax_amount=tax_amount,
                currency_code=currency_code,
                document_type=document_type,
                status="extracted",
            )
        )

    async def find_duplicate(self, tenant_id: uuid.UUID, checksum: str) -> Document | None:
        result = await self._db.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.checksum_sha256 == checksum,
                Document.is_duplicate == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def find_content_duplicate(
        self,
        tenant_id: uuid.UUID,
        *,
        exclude_document_id: uuid.UUID,
        original_filename: str,
        vendor_name: str | None,
        document_date: datetime | None,
        total_amount: Decimal | None,
    ) -> Document | None:
        """
        Find an already-extracted document that is the same invoice/receipt in
        substance, regardless of file bytes.

        Checksum-based dedup misses the same invoice arriving twice through
        different channels (e.g. synced via both Gmail and Outlook) — each
        copy re-encodes slightly differently, so the SHA256 never matches even
        though the content is identical. Matched on vendor + exact date +
        exact amount, refined by the invoice number embedded in the filename
        when one is extractable.

        The invoice number is the deciding signal, not vendor+date+amount:
        verified live against production data that a single vendor routinely
        issues several invoices to the same customer with the identical total
        on the identical date (daily delivery batches) — 20 of an initial 58
        vendor+date+amount matches turned out to be genuinely different
        invoices once checked against their filename-embedded invoice number.
        So when BOTH sides have an extractable number, they must match, full
        stop — vendor+date+amount cannot override a number mismatch. Only
        when a number can't be extracted from one or both filenames does this
        fall back to vendor+date+amount alone (batch statements like
        "1941 AFS Invoices.pdf" have no single invoice number to extract).

        Vendor names are compared as significant lowercase tokens rather than
        exact strings ("Alex Food Service" vs "Alex Food Service Corp.") so a
        legal-suffix difference alone doesn't defeat the match.
        """
        if not vendor_name or document_date is None or total_amount is None:
            return None

        candidates = (
            await self._db.execute(
                select(Document).where(
                    Document.tenant_id == tenant_id,
                    Document.id != exclude_document_id,
                    Document.is_duplicate == False,  # noqa: E712
                    Document.document_date == document_date,
                    Document.total_amount == total_amount,
                    Document.vendor_name.isnot(None),
                )
            )
        ).scalars().all()

        target_tokens = _vendor_tokens(vendor_name)
        if not target_tokens:
            return None

        target_inv_num = _extract_invoice_number(original_filename)
        for candidate in candidates:
            if not (_vendor_tokens(candidate.vendor_name) & target_tokens):
                continue
            candidate_inv_num = _extract_invoice_number(candidate.original_filename)
            if target_inv_num and candidate_inv_num and target_inv_num != candidate_inv_num:
                continue  # different invoice numbers — not the same document, however close the rest looks
            return candidate
        return None

    async def mark_duplicate(self, document_id: uuid.UUID, *, duplicate_of: uuid.UUID) -> None:
        await self._db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(is_duplicate=True, duplicate_of=duplicate_of, status="error",
                    error_message="Duplicate of existing document")
        )

    async def save_ocr_result(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        provider: str,
        raw_response: dict,
        extracted_text: str,
        confidence_score: Decimal,
        page_count: int,
        processing_time_ms: int,
    ) -> OCRResult:
        ocr = OCRResult(
            tenant_id=tenant_id,
            document_id=document_id,
            provider=provider,
            raw_response=raw_response,
            extracted_text=extracted_text,
            confidence_score=confidence_score,
            page_count=page_count,
            processing_time_ms=processing_time_ms,
            processed_at=datetime.now(UTC),
        )
        self._db.add(ocr)
        await self._db.flush()
        return ocr

    async def save_line_items(
        self,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        ocr_result_id: uuid.UUID,
        items: list[dict],
    ) -> None:
        for item in items:
            li = ExtractedLineItem(
                tenant_id=tenant_id,
                document_id=document_id,
                ocr_result_id=ocr_result_id,
                **item,
            )
            self._db.add(li)

    async def get_latest_ocr_result(self, document_id: uuid.UUID) -> OCRResult | None:
        result = await self._db.execute(
            select(OCRResult)
            .where(OCRResult.document_id == document_id)
            .order_by(OCRResult.processed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_line_items(self, document_id: uuid.UUID) -> list[ExtractedLineItem]:
        result = await self._db.execute(
            select(ExtractedLineItem)
            .where(ExtractedLineItem.document_id == document_id)
            .order_by(ExtractedLineItem.created_at)
        )
        return list(result.scalars().all())

    async def delete(self, document_id: uuid.UUID) -> None:
        doc = await self._db.get(Document, document_id)
        if doc:
            await self._db.delete(doc)
