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


@router.post("/recategorize-all", response_model=APIResponse[dict])
async def trigger_recategorize_all(
    user: ManagerDep,
    db: AsyncSessionDep,
    limit: int = Query(1000, ge=1, le=5000),
) -> dict:
    """Re-run AI categorization for ALL uncategorized expenses of the tenant.

    Use after improving the categorization rules to backfill existing rows. The
    deterministic keyword map means most re-categorize for free (no AI cost)."""
    repo = ExpenseRepository(db)
    rows, total = await repo.list_expenses(
        tenant_id=user.tenant_id, uncategorized_only=True, page=1, limit=limit
    )

    from app.workers.tasks.ai_categorize import categorize_expense
    for expense in rows:
        categorize_expense.apply_async(
            kwargs={"expense_id": str(expense.id), "tenant_id": str(user.tenant_id)},
            queue="ai",
        )
    logger.info(
        "expense_recategorize_all_queued",
        tenant_id=str(user.tenant_id),
        queued=len(rows),
        total_uncategorized=total,
    )
    return {
        "data": {"queued": len(rows), "total_uncategorized": total},
        "errors": None,
    }


@router.post("/purge-range", response_model=APIResponse[dict])
async def purge_expenses_in_range(
    user: ManagerDep,
    db: AsyncSessionDep,
    start: date = Query(..., description="Inclusive start date (YYYY-MM-DD)"),
    end: date = Query(..., description="Inclusive end date (YYYY-MM-DD)"),
    location_id: uuid.UUID | None = Query(None),
    include_overridden: bool = Query(
        False, description="Also delete user-overridden expenses (default keeps them)"
    ),
) -> dict:
    """Delete all expenses in a date range to reset a corrupted reporting period.

    Use before re-uploading/reprocessing statements when a month was poisoned by
    duplicated or phantom rows (e.g. inflated payroll). Originals/documents are
    untouched — only Expense rows are removed. User-overridden rows are preserved
    unless include_overridden is set."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=UTC)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=UTC)

    repo = ExpenseRepository(db)
    deleted = await repo.delete_in_range(
        tenant_id=user.tenant_id,
        start=start_dt,
        end=end_dt,
        location_id=location_id,
        include_overridden=include_overridden,
    )
    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="expense.purge_range",
        user_id=user.user_id,
        entity_type="expense",
        entity_id=None,
        new_value={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location_id": str(location_id) if location_id else None,
            "include_overridden": include_overridden,
            "deleted": deleted,
        },
    )
    await db.commit()
    logger.info(
        "expense_purge_range",
        tenant_id=str(user.tenant_id),
        start=start.isoformat(),
        end=end.isoformat(),
        deleted=deleted,
    )
    return {"data": {"deleted": deleted}, "errors": None}


@router.get("/hst-summary")
async def hst_summary(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    period_start: str = Query(..., description="ISO date YYYY-MM-DD"),
    period_end: str = Query(..., description="ISO date YYYY-MM-DD"),
    location_id: uuid.UUID | None = Query(None),
) -> dict:
    """Recoverable HST/GST (Input Tax Credits) rolled up by month and quarter.

    HST paid on expenses is an Input Tax Credit — recoverable against HST
    collected on sales at GST/HST filing time. This surfaces the ITC pool per
    period so nothing is left unclaimed, and flags expenses missing a captured
    tax amount (potential un-claimed credits)."""
    try:
        start = datetime.strptime(period_start, "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(period_end, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD") from exc

    repo = ExpenseRepository(db)
    rows = await repo.hst_by_month(
        user.tenant_id, start=start, end=end, location_id=location_id
    )
    collected = await repo.hst_collected_by_month(
        user.tenant_id, start=start, end=end, location_id=location_id
    )

    months = []
    quarters: dict[tuple[int, int], dict] = {}
    total_itc = Decimal("0")
    total_collected = Decimal("0")
    total_missing = 0
    # Union of months that have expenses (ITCs) OR Toast sales (HST collected).
    all_keys = {(yr, mo) for yr, mo, *_ in rows} | set(collected.keys())
    row_map = {(yr, mo): (tax, exp, cnt, miss) for yr, mo, tax, exp, cnt, miss in rows}

    for (yr, mo) in sorted(all_keys):
        tax_total, expense_total, doc_count, missing = row_map.get(
            (yr, mo), (Decimal("0"), Decimal("0"), 0, 0)
        )
        hst_collected = collected.get((yr, mo), Decimal("0"))
        net_remit = hst_collected - tax_total
        q = (mo - 1) // 3 + 1
        months.append(
            {
                "period_label": f"{yr}-{mo:02d}",
                "year": yr,
                "month": mo,
                "quarter": q,
                "hst_total": str(tax_total),
                "hst_collected": str(hst_collected),
                "net_remittance": str(net_remit),
                "expense_total": str(expense_total),
                "expense_count": doc_count,
                "missing_tax_count": missing,
            }
        )
        agg = quarters.setdefault(
            (yr, q), {"year": yr, "quarter": q, "hst_total": Decimal("0"),
                      "hst_collected": Decimal("0"), "expense_total": Decimal("0"),
                      "expense_count": 0, "missing_tax_count": 0}
        )
        agg["hst_total"] += tax_total
        agg["hst_collected"] += hst_collected
        agg["expense_total"] += expense_total
        agg["expense_count"] += doc_count
        agg["missing_tax_count"] += missing
        total_itc += tax_total
        total_collected += hst_collected
        total_missing += missing

    quarter_list = [
        {
            "period_label": f"{v['year']} Q{v['quarter']}",
            "year": v["year"],
            "quarter": v["quarter"],
            "hst_total": str(v["hst_total"]),
            "hst_collected": str(v["hst_collected"]),
            "net_remittance": str(v["hst_collected"] - v["hst_total"]),
            "expense_total": str(v["expense_total"]),
            "expense_count": v["expense_count"],
            "missing_tax_count": v["missing_tax_count"],
        }
        for v in sorted(quarters.values(), key=lambda x: (x["year"], x["quarter"]))
    ]

    return {
        "data": {
            "months": months,
            "quarters": quarter_list,
            "total_hst": str(total_itc),
            "total_hst_collected": str(total_collected),
            "total_net_remittance": str(total_collected - total_itc),
            "total_missing_tax_count": total_missing,
        },
        "errors": None,
    }


@router.post("/hst-backfill")
async def hst_backfill(user: ManagerDep, limit: int = Query(500, ge=1, le=2000)) -> dict:
    """Re-read stored OCR text for extracted invoices/receipts missing a tax
    amount and backfill HST/GST (cheap Claude haiku, no re-OCR). Idempotent."""
    from app.workers.tasks.hst_backfill import backfill_hst

    task = backfill_hst.delay(str(user.tenant_id), limit)
    return {"data": {"task_id": task.id, "status": "queued"}, "errors": None}


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
