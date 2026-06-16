import uuid
from datetime import date, datetime, UTC
from decimal import Decimal, InvalidOperation

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.core.deps import CurrentUserDep, ManagerDep
from app.db.models.expense import EXPENSE_CATEGORIES
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.document_repo import DocumentRepository
from app.db.repositories.expense_repo import ExpenseRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse, PaginatedMeta, PaginatedResponse
from app.schemas.expense import ExpenseCategoryOverrideRequest, ExpenseResponse

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("", response_model=PaginatedResponse[ExpenseResponse])
async def list_expenses(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = Query(None),
    category: str | None = Query(None),
    vendor_name: str | None = Query(None),
    uncategorized_only: bool = Query(False),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    repo = ExpenseRepository(db)
    rows, total = await repo.list_expenses(
        tenant_id=user.tenant_id,
        location_id=location_id,
        category=category,
        vendor_name=vendor_name,
        uncategorized_only=uncategorized_only,
        page=page,
        limit=limit,
    )
    return {
        "data": [ExpenseResponse.model_validate(r) for r in rows],
        "meta": PaginatedMeta(page=page, limit=limit, total=total),
        "errors": None,
    }


@router.post("", response_model=APIResponse[ExpenseResponse], status_code=201)
async def create_manual_expense(
    user: ManagerDep,
    db: AsyncSessionDep,
    expense_date: date = Form(...),
    description: str = Form(...),
    amount: str = Form(...),
    location_id: str | None = Form(None),
    category: str | None = Form(None),
    receipt: UploadFile | None = File(None),
) -> dict:
    """Manually-entered expense (date + description + amount), with an optional
    receipt (PDF/image) that gets OCR'd and AI-categorized like any other upload."""
    try:
        amount_decimal = Decimal(amount)
    except InvalidOperation as exc:
        raise HTTPException(status_code=422, detail="Invalid amount") from exc

    if category and category not in EXPENSE_CATEGORIES:
        raise HTTPException(status_code=422, detail=f"Invalid category. Must be one of: {sorted(EXPENSE_CATEGORIES)}")

    loc_id = uuid.UUID(location_id) if location_id else None
    if loc_id is None:
        from sqlalchemy import select
        from app.db.models.location import Location
        locations = (await db.execute(
            select(Location.id).where(Location.tenant_id == user.tenant_id)
        )).scalars().all()
        if len(locations) == 1:
            loc_id = locations[0]

    document_id = None
    if receipt is not None and receipt.filename:
        from app.services.document_service import ingest_document
        from app.services.virus_scan import scan_upload, VirusScanError, ALLOWED_MIME_TYPES

        file_bytes = await receipt.read()
        mime_type = receipt.content_type or "application/octet-stream"
        if mime_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=422, detail=f"Unsupported file type: {mime_type}")
        try:
            scan_upload(file_bytes, receipt.filename, mime_type)
        except VirusScanError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        doc, _is_duplicate = await ingest_document(
            file_bytes=file_bytes,
            original_filename=receipt.filename,
            mime_type=mime_type,
            tenant_id=user.tenant_id,
            created_by=user.user_id,
            repo=DocumentRepository(db),
            location_id=loc_id,
            source="manual_expense_receipt",
        )
        document_id = doc.id

    repo = ExpenseRepository(db)
    expense = await repo.create_from_document(
        tenant_id=user.tenant_id,
        document_id=document_id,
        vendor_name=description,
        amount=amount_decimal,
        currency_code="CAD",
        location_id=loc_id,
        created_by=user.user_id,
        expense_date=datetime(expense_date.year, expense_date.month, expense_date.day, tzinfo=UTC),
        category=category,
        user_overridden=bool(category),
    )

    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="expense.created_manual",
        user_id=user.user_id,
        entity_type="expense",
        entity_id=expense.id,
        new_value={"vendor_name": description, "amount": str(amount_decimal), "category": category},
    )
    await db.commit()

    if not category:
        from app.workers.tasks.ai_categorize import categorize_expense
        categorize_expense.apply_async(
            kwargs={"expense_id": str(expense.id), "tenant_id": str(user.tenant_id)},
            queue="ai",
        )

    logger.info("expense_created_manual", expense_id=str(expense.id), has_receipt=document_id is not None)
    return {"data": ExpenseResponse.model_validate(expense), "errors": None}


@router.get("/{expense_id}", response_model=APIResponse[ExpenseResponse])
async def get_expense(expense_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    repo = ExpenseRepository(db)
    expense = await repo.get(user.tenant_id, expense_id)
    return {"data": ExpenseResponse.model_validate(expense), "errors": None}


@router.patch("/{expense_id}/category", response_model=APIResponse[ExpenseResponse])
async def override_category(
    expense_id: uuid.UUID,
    body: ExpenseCategoryOverrideRequest,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    repo = ExpenseRepository(db)
    expense = await repo.get(user.tenant_id, expense_id)
    old_category = expense.category
    expense = await repo.override_category(user.tenant_id, expense_id, body.category)
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="expense.category_overridden",
        user_id=user.user_id,
        entity_type="expense",
        entity_id=expense_id,
        old_value={"category": old_category},
        new_value={"category": body.category},
    )
    await db.commit()
    logger.info(
        "expense_category_overridden",
        expense_id=str(expense_id),
        category=body.category,
        by=str(user.user_id),
    )
    return {"data": ExpenseResponse.model_validate(expense), "errors": None}


@router.post("/{expense_id}/recategorize", response_model=APIResponse[dict])
async def trigger_recategorize(
    expense_id: uuid.UUID,
    user: ManagerDep,
    db: AsyncSessionDep,
) -> dict:
    """Re-run AI categorization for an expense."""
    repo = ExpenseRepository(db)
    expense = await repo.get(user.tenant_id, expense_id)

    from app.workers.tasks.ai_categorize import categorize_expense
    categorize_expense.apply_async(
        kwargs={"expense_id": str(expense.id), "tenant_id": str(user.tenant_id)},
        queue="ai",
    )
    return {"data": {"queued": True, "expense_id": str(expense_id)}, "errors": None}


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(expense_id: uuid.UUID, user: ManagerDep, db: AsyncSessionDep) -> None:
    repo = ExpenseRepository(db)
    await repo.delete(user.tenant_id, expense_id)
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="expense.deleted",
        user_id=user.user_id,
        entity_type="expense",
        entity_id=expense_id,
    )
    await db.commit()
