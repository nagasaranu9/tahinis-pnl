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
