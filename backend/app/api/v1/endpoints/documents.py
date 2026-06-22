import uuid

import structlog
from fastapi import APIRouter, File, Form, Query, UploadFile

from fastapi import HTTPException
from app.core.deps import CurrentUserDep, ManagerDep
from app.core.exceptions import ForbiddenError
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.expense_repo import ExpenseRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.document import (
    DocumentResponse,
    LineItemCorrectionRequest,
    LineItemResponse,
    OCRResultResponse,
)
from app.services.document_service import ingest_document
from app.services.storage_service import get_signed_url
from app.services.virus_scan import scan_upload, VirusScanError, ALLOWED_MIME_TYPES

router = APIRouter()
logger = structlog.get_logger(__name__)


def _to_response(doc: object, include_url: bool = False) -> DocumentResponse:
    resp = DocumentResponse.model_validate(doc)
    if include_url:
        try:
            resp.download_url = get_signed_url(doc.storage_path)  # type: ignore[attr-defined]
        except Exception:
            resp.download_url = None
    return resp


@router.post("/upload", response_model=APIResponse[DocumentResponse], status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    location_id: str | None = Form(None),
    user: CurrentUserDep = ...,
    db: AsyncSessionDep = ...,
) -> dict:
    file_bytes = await file.read()
    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"

    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {mime_type}")

    try:
        scan_upload(file_bytes, filename, mime_type)
    except VirusScanError as exc:
        logger.warning("upload_rejected_virus_scan", filename=filename, reason=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    loc_id = uuid.UUID(location_id) if location_id else None
    repo = DocumentRepository(db)

    if loc_id is None:
        # No location explicitly chosen at upload time — default to the tenant's
        # sole location so expenses aren't orphaned with location_id=NULL (which
        # silently fails the P&L location filter once a frontend location picker
        # sends a real location_id).
        from sqlalchemy import select
        from app.db.models.location import Location
        locations = (await db.execute(
            select(Location.id).where(Location.tenant_id == user.tenant_id)
        )).scalars().all()
        if len(locations) == 1:
            loc_id = locations[0]

    doc, is_duplicate = await ingest_document(
        file_bytes=file_bytes,
        original_filename=filename,
        mime_type=mime_type,
        tenant_id=user.tenant_id,
        created_by=user.user_id,
        repo=repo,
        location_id=loc_id,
    )
    return {"data": _to_response(doc), "errors": None}


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    status: str | None = Query(None),
    document_type: str | None = Query(None),
    location_id: uuid.UUID | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    repo = DocumentRepository(db)
    docs, total = await repo.list(
        user.tenant_id,
        status=status,
        document_type=document_type,
        location_id=location_id,
        page=page,
        limit=limit,
    )
    return {
        "data": [_to_response(d) for d in docs],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.get("/{document_id}", response_model=APIResponse[DocumentResponse])
async def get_document(document_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = DocumentRepository(db)
    doc = await repo.get(user.tenant_id, document_id)
    return {"data": _to_response(doc, include_url=True), "errors": None}


@router.delete("", response_model=APIResponse[dict])
async def delete_all_documents(user: ManagerDep, db: AsyncSessionDep) -> dict:
    """Delete ALL documents for this tenant. Irreversible — DB records removed, S3 files stay."""
    repo = DocumentRepository(db)
    from sqlalchemy import select, delete as sa_delete
    from app.db.models.document import Document
    ids_result = await db.execute(
        select(Document.id).where(Document.tenant_id == user.tenant_id)
    )
    ids = [r[0] for r in ids_result.fetchall()]
    expenses_deleted = 0
    if ids:
        # Cascade: remove expenses derived from these documents so the P&L doesn't
        # keep orphaned rows after the documents are gone.
        expenses_deleted = await ExpenseRepository(db).delete_by_document_ids(
            user.tenant_id, ids
        )
        await db.execute(
            sa_delete(Document).where(
                Document.tenant_id == user.tenant_id
            )
        )
        await AuditRepository(db).log(
            tenant_id=user.tenant_id,
            action="document.bulk_deleted",
            user_id=user.user_id,
            entity_type="document",
            entity_id=user.tenant_id,
            old_value={"count": len(ids), "expenses_deleted": expenses_deleted},
        )
    await db.commit()
    return {"data": {"deleted": len(ids), "expenses_deleted": expenses_deleted}, "errors": None}


@router.delete("/{document_id}", response_model=APIResponse[None])
async def delete_document(document_id: uuid.UUID, user: ManagerDep, db: AsyncSessionDep) -> dict:
    repo = DocumentRepository(db)
    doc = await repo.get(user.tenant_id, document_id)
    # Cascade: drop expenses derived from this document (incl. overridden) so the
    # P&L doesn't keep orphaned rows after the document is deleted.
    exp_deleted = await ExpenseRepository(db).delete_by_document(
        user.tenant_id, document_id, include_overridden=True
    )
    # storage_path retained for audit. File stays in S3 (immutable source rule). Only DB record deleted.
    await repo.delete(document_id)
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="document.deleted",
        user_id=user.user_id,
        entity_type="document",
        entity_id=document_id,
        old_value={"filename": doc.original_filename, "storage_path": doc.storage_path},
    )
    await db.commit()
    return {"data": None, "errors": None}


@router.post("/{document_id}/reprocess", response_model=APIResponse[DocumentResponse])
async def reprocess_document(document_id: uuid.UUID, user: ManagerDep, db: AsyncSessionDep) -> dict:
    repo = DocumentRepository(db)
    doc = await repo.get(user.tenant_id, document_id)

    # Wipe prior (non-user-overridden) expenses for this doc so re-extraction
    # starts clean — otherwise dedup-by-vendor blocks corrected rows and stale
    # miscategorized rows survive.
    from app.db.repositories.expense_repo import ExpenseRepository
    deleted = await ExpenseRepository(db).delete_by_document(user.tenant_id, document_id)

    await repo.update_status(document_id, "pending")
    await db.commit()

    from app.workers.tasks.ocr_process import process_document
    process_document.delay(str(document_id), str(user.tenant_id))

    logger.info("document_reprocess_queued", document_id=str(document_id), expenses_deleted=deleted)
    await db.refresh(doc)
    return {"data": _to_response(doc), "errors": None}


@router.post("/reprocess-bank-statements", response_model=APIResponse[dict])
async def reprocess_all_bank_statements(
    user: ManagerDep,
    db: AsyncSessionDep,
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    """Re-run OCR + categorization on every bank statement for the tenant.

    Wipes prior (non-user-overridden) expenses per document, then re-queues
    extraction so corrected categorization rules (Food Cost, Rent-via-AMEX,
    bank-fee/interest, non-operating exclusions) apply across all months at once."""
    from app.db.repositories.expense_repo import ExpenseRepository

    doc_repo = DocumentRepository(db)
    exp_repo = ExpenseRepository(db)
    docs, total = await doc_repo.list(
        user.tenant_id, document_type="bank_statement", page=1, limit=limit
    )

    from app.workers.tasks.ocr_process import process_document

    deleted_total = 0
    for doc in docs:
        deleted_total += await exp_repo.delete_by_document(user.tenant_id, doc.id)
        await doc_repo.update_status(doc.id, "pending")
    await db.commit()

    for doc in docs:
        process_document.delay(str(doc.id), str(user.tenant_id))

    logger.info(
        "bank_statements_bulk_reprocess_queued",
        tenant_id=str(user.tenant_id),
        documents=len(docs),
        expenses_deleted=deleted_total,
    )
    return {
        "data": {
            "queued": len(docs),
            "total_bank_statements": total,
            "expenses_deleted": deleted_total,
        },
        "errors": None,
    }


@router.get("/{document_id}/ocr", response_model=APIResponse[OCRResultResponse])
async def get_ocr_result(document_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = DocumentRepository(db)
    await repo.get(user.tenant_id, document_id)  # assert ownership
    ocr = await repo.get_latest_ocr_result(document_id)
    if ocr is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("OCR result not available yet")
    return {"data": OCRResultResponse.model_validate(ocr), "errors": None}


@router.get("/{document_id}/line-items", response_model=APIResponse[list[LineItemResponse]])
async def list_line_items(document_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = DocumentRepository(db)
    await repo.get(user.tenant_id, document_id)  # assert ownership
    items = await repo.get_line_items(document_id)
    return {"data": [LineItemResponse.model_validate(i) for i in items], "errors": None}


@router.patch("/{document_id}/line-items/{line_item_id}", response_model=APIResponse[LineItemResponse])
async def correct_line_item(
    document_id: uuid.UUID,
    line_item_id: uuid.UUID,
    body: LineItemCorrectionRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    repo = DocumentRepository(db)
    await repo.get(user.tenant_id, document_id)  # assert ownership

    from app.db.models.document import ExtractedLineItem
    from sqlalchemy import update, select
    updates = body.model_dump(exclude_none=True)
    if updates:
        from datetime import UTC, datetime
        updates["manually_corrected"] = True
        updates["corrected_by"] = user.user_id
        updates["corrected_at"] = datetime.now(UTC)
        await db.execute(
            update(ExtractedLineItem)
            .where(ExtractedLineItem.id == line_item_id, ExtractedLineItem.document_id == document_id)
            .values(**updates)
        )

    result = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(ExtractedLineItem)
        .where(ExtractedLineItem.id == line_item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Line item not found")
    return {"data": LineItemResponse.model_validate(item), "errors": None}
