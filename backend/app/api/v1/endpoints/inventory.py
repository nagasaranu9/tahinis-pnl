"""Weekly COGS inventory-count upload + reporting.

Upload the AFS inventory spreadsheet once a week; it is parsed into priced line
items, chained against the prior week, and surfaced as per-category and total
COGS (with COGS % against live net-sales revenue). Standalone — does not alter
the bank-basis P&L.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog
from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from sqlalchemy import and_, select

from app.core.deps import CurrentUserDep
from app.db.models.inventory import INVENTORY_CATEGORIES, InventoryCount, InventoryCountItem
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.services.inventory.cogs_parser import parse_cogs_sheet
from app.services.inventory.cogs_service import compute_cogs

router = APIRouter()
logger = structlog.get_logger(__name__)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Documents uploaded through the COGS invoice panel. Prefixed "manual" so the
# ingest pipeline treats them as deliberate (no non-financial filename filter),
# and distinct so only these feed a week's auto-purchases — never stray receipts.
from app.services.inventory.cogs_service import COGS_INVOICE_SOURCE


async def _resolve_location(db, tenant_id: uuid.UUID, location_id: str | None) -> uuid.UUID | None:
    if location_id:
        return uuid.UUID(location_id)
    from app.db.models.location import Location
    locs = (await db.execute(
        select(Location.id).where(Location.tenant_id == tenant_id)
    )).scalars().all()
    return locs[0] if len(locs) == 1 else None


def _header(count: InventoryCount) -> dict:
    return {
        "id": str(count.id),
        "week_ending": count.week_ending.isoformat(),
        "location_id": str(count.location_id) if count.location_id else None,
        "original_filename": count.original_filename,
        "created_at": count.created_at.isoformat() if count.created_at else None,
    }


@router.post("/cogs/upload", response_model=APIResponse[dict], status_code=201)
async def upload_cogs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    file: UploadFile = File(...),
    week_ending: str = Form(..., description="YYYY-MM-DD the count represents"),
    location_id: str | None = Form(None),
    purchases: str | None = Form(None, description="Manual total purchases for the week"),
    net_sales: str | None = Form(None, description="Manual net sales override"),
) -> dict:
    name = (file.filename or "").lower()
    if not (name.endswith(".xlsx") or name.endswith(".xlsm")):
        raise HTTPException(status_code=422, detail="Upload an .xlsx inventory sheet")
    try:
        we = date.fromisoformat(week_ending)
    except ValueError:
        raise HTTPException(status_code=422, detail="week_ending must be YYYY-MM-DD")

    file_bytes = await file.read()
    try:
        parsed = parse_cogs_sheet(file_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cogs_parse_failed", error=str(exc), filename=file.filename)
        raise HTTPException(status_code=422, detail=f"Could not parse sheet: {exc}") from exc
    if not parsed.items:
        raise HTTPException(status_code=422, detail="No priced items found — check the sheet format")

    loc_id = await _resolve_location(db, user.tenant_id, location_id)

    # Store the raw file (best-effort — never block the upload on storage).
    storage_path = None
    try:
        from app.services.storage_service import upload_document
        storage_path, _ = upload_document(file_bytes, user.tenant_id, file.filename or "cogs.xlsx", _XLSX_MIME)
    except Exception as exc:  # noqa: BLE001
        logger.warning("cogs_storage_failed", error=str(exc))

    # Re-upload for the same week replaces the prior submission.
    existing = (await db.execute(
        select(InventoryCount).where(and_(
            InventoryCount.tenant_id == user.tenant_id,
            InventoryCount.location_id == loc_id,
            InventoryCount.week_ending == we,
        ))
    )).scalars().first()
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    ending = parsed.category_ending
    category_totals = {
        c: {
            "ending": str(ending.get(c, 0)),
            "purchases": str(parsed.purchases.get(c, 0)),
        }
        for c in INVENTORY_CATEGORIES
    }

    def _money_opt(v: str | None):
        if v is None or str(v).strip() == "":
            return None
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=422, detail="purchases / net_sales must be numbers")

    count = InventoryCount(
        tenant_id=user.tenant_id,
        location_id=loc_id,
        week_ending=we,
        original_filename=file.filename,
        storage_path=storage_path,
        category_totals=category_totals,
        purchases_override=_money_opt(purchases),
        net_sales_override=_money_opt(net_sales),
        created_by=user.user_id,
    )
    db.add(count)
    await db.flush()
    for it in parsed.items:
        db.add(InventoryCountItem(tenant_id=user.tenant_id, count_id=count.id, **it))
    await db.flush()

    report = await compute_cogs(db, count)
    await db.commit()
    return {"data": {**_header(count), "report": report}, "errors": None}


@router.post("/cogs/invoices", response_model=APIResponse[list], status_code=201)
async def upload_invoices(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    files: list[UploadFile] = File(...),
    location_id: str | None = Form(None),
) -> dict:
    """Upload supplier invoices — OCR'd asynchronously into Food/Beverage/
    Packaging expenses that auto-feed the matching week's COGS purchases."""
    from app.db.repositories.document_repo import DocumentRepository
    from app.services.document_service import ingest_document
    from app.workers.tasks.ocr_process import process_document

    loc_id = await _resolve_location(db, user.tenant_id, location_id)
    repo = DocumentRepository(db)
    out = []
    for f in files:
        data = await f.read()
        mime = f.content_type or "application/octet-stream"
        try:
            doc, dup = await ingest_document(
                file_bytes=data, original_filename=f.filename or "invoice",
                mime_type=mime, tenant_id=user.tenant_id, created_by=user.user_id,
                repo=repo, location_id=loc_id, source=COGS_INVOICE_SOURCE,
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cogs_invoice_ingest_failed", error=str(exc), filename=f.filename)
            out.append({"filename": f.filename, "status": "error", "error": str(exc)[:200]})
            continue
        if doc is None:
            out.append({"filename": f.filename, "status": "ignored"})
            continue
        if not dup:
            process_document.delay(str(doc.id), str(user.tenant_id))
        out.append({
            "id": str(doc.id), "filename": f.filename,
            "status": "duplicate" if dup else "processing",
        })
    return {"data": out, "errors": None}


@router.get("/cogs/{count_id}/invoices", response_model=APIResponse[dict])
async def list_week_invoices(count_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    """Invoice-sourced expenses that fall in a week's count period."""
    from app.db.models.document import Document
    from app.db.models.expense import Expense
    from app.services.inventory.cogs_service import (
        COGS_INVOICE_SOURCE, _INVOICE_EXPENSE_CATEGORIES, _prior_count, _purchase_window,
    )

    count = (await db.execute(
        select(InventoryCount).where(and_(
            InventoryCount.id == count_id, InventoryCount.tenant_id == user.tenant_id,
        ))
    )).scalars().first()
    if count is None:
        raise HTTPException(status_code=404, detail="Count not found")

    prior = await _prior_count(db, count.tenant_id, count.location_id, count.week_ending)
    start, end = _purchase_window(count.week_ending, prior)
    conds = [
        Expense.tenant_id == user.tenant_id,
        Expense.expense_date >= start, Expense.expense_date <= end,
        Expense.category.in_(_INVOICE_EXPENSE_CATEGORIES),
        Document.source == COGS_INVOICE_SOURCE,
    ]
    if count.location_id is not None:
        conds.append(Expense.location_id == count.location_id)
    rows = (await db.execute(
        select(Expense.expense_date, Expense.vendor_name, Expense.amount, Expense.category,
               Document.original_filename, Document.document_type)
        .join(Document, Expense.document_id == Document.id).where(and_(*conds))
        .order_by(Expense.expense_date)
    )).all()
    invoices = [{
        "date": d.date().isoformat() if d else None,
        "vendor_name": v, "amount": str(a) if a is not None else "0",
        "category": c, "filename": fn, "document_type": dt,
    } for d, v, a, c, fn, dt in rows]
    return {"data": {
        "window_start": start.date().isoformat(), "window_end": end.date().isoformat(),
        "invoices": invoices,
    }, "errors": None}


@router.get("/cogs", response_model=APIResponse[list])
async def list_cogs(
    user: CurrentUserDep,
    db: AsyncSessionDep,
    location_id: uuid.UUID | None = None,
) -> dict:
    conds = [InventoryCount.tenant_id == user.tenant_id]
    if location_id is not None:
        conds.append(InventoryCount.location_id == location_id)
    counts = (await db.execute(
        select(InventoryCount).where(and_(*conds)).order_by(InventoryCount.week_ending.desc())
    )).scalars().all()
    out = []
    for c in counts:
        report = await compute_cogs(db, c)
        out.append({**_header(c), "totals": report["totals"], "net_sales": report["net_sales"]})
    return {"data": out, "errors": None}


@router.get("/cogs/{count_id}", response_model=APIResponse[dict])
async def get_cogs(count_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    count = (await db.execute(
        select(InventoryCount).where(and_(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == user.tenant_id,
        ))
    )).scalars().first()
    if count is None:
        raise HTTPException(status_code=404, detail="Count not found")
    items = (await db.execute(
        select(InventoryCountItem).where(InventoryCountItem.count_id == count.id)
        .order_by(InventoryCountItem.sort_order)
    )).scalars().all()
    report = await compute_cogs(db, count)
    item_rows = [{
        "category": i.category,
        "item_name": i.item_name,
        "pack_size": i.pack_size,
        "unit": i.unit,
        "cases": str(i.cases) if i.cases is not None else None,
        "packs": str(i.packs) if i.packs is not None else None,
        "weight": str(i.weight) if i.weight is not None else None,
        "unit_price": str(i.unit_price) if i.unit_price is not None else None,
        "extended_total": str(i.extended_total),
    } for i in items]
    return {"data": {**_header(count), "report": report, "items": item_rows}, "errors": None}


@router.patch("/cogs/{count_id}", response_model=APIResponse[dict])
async def patch_cogs(
    count_id: uuid.UUID,
    user: CurrentUserDep,
    db: AsyncSessionDep,
    body: dict = Body(...),
) -> dict:
    """Set the purchases / net-sales overrides for a week (null clears → auto)."""
    count = (await db.execute(
        select(InventoryCount).where(and_(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == user.tenant_id,
        ))
    )).scalars().first()
    if count is None:
        raise HTTPException(status_code=404, detail="Count not found")

    def _parse(key):
        if key not in body:
            return False, None
        v = body[key]
        if v is None or str(v).strip() == "":
            return True, None
        try:
            return True, Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=422, detail=f"{key} must be a number")

    has_p, p = _parse("purchases")
    if has_p:
        count.purchases_override = p
    has_n, n = _parse("net_sales")
    if has_n:
        count.net_sales_override = n
    await db.flush()
    report = await compute_cogs(db, count)
    await db.commit()
    return {"data": {**_header(count), "report": report}, "errors": None}


@router.delete("/cogs/{count_id}", response_model=APIResponse[dict])
async def delete_cogs(count_id: uuid.UUID, user: CurrentUserDep, db: AsyncSessionDep) -> dict:
    count = (await db.execute(
        select(InventoryCount).where(and_(
            InventoryCount.id == count_id,
            InventoryCount.tenant_id == user.tenant_id,
        ))
    )).scalars().first()
    if count is None:
        raise HTTPException(status_code=404, detail="Count not found")
    await db.delete(count)
    await db.commit()
    return {"data": {"deleted": str(count_id)}, "errors": None}
