from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.document import Document, ExtractedLineItem, OCRResult


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
    ) -> None:
        await self._db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                vendor_name=vendor_name,
                document_date=document_date,
                total_amount=total_amount,
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
