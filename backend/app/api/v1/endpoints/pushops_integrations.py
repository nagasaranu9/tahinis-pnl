import uuid
from datetime import date
from decimal import Decimal

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import ManagerDep
from app.db.repositories.audit_repo import AuditRepository
from app.db.repositories.expense_repo import ExpenseRepository
from app.db.session import AsyncSessionDep
from app.schemas.common import APIResponse
from app.schemas.labor import PushOpsImportResult
from app.services.labor.pushops_import import (
    PushOpsParseError,
    parse_pushops_csv,
    to_datetime,
)

router = APIRouter()
logger = structlog.get_logger(__name__)

_MAX_BYTES = 5 * 1024 * 1024


async def _resolve_location(
    db: AsyncSession, tenant_id: uuid.UUID, location_id: str | None
) -> uuid.UUID | None:
    if location_id:
        return uuid.UUID(location_id)
    # Auto-pick when the tenant has exactly one location (single-location operators).
    from sqlalchemy import select
    from app.db.models.location import Location

    locs = (
        await db.execute(select(Location.id).where(Location.tenant_id == tenant_id))
    ).scalars().all()
    return locs[0] if len(locs) == 1 else None


@router.post("/import-csv", response_model=APIResponse[PushOpsImportResult])
async def import_pushops_csv(
    user: ManagerDep,
    db: AsyncSessionDep,
    file: UploadFile = File(...),
    location_id: str | None = Form(None),
    pay_date: date | None = Form(None),
) -> dict:
    """Import a PushOperations payroll CSV export as Payroll-category expenses.

    PushOps has no open API on lower tiers, so the operator downloads the payroll
    report as CSV and uploads it here. Each row becomes a Payroll expense that
    flows into the P&L Labor Cost line. Re-importing the same file is safe —
    identical rows are deduplicated.

    `pay_date` is an optional fallback used for rows whose date can't be parsed
    (or summary exports with no date column).
    """
    file_bytes = await file.read()
    if len(file_bytes) > _MAX_BYTES:
        raise HTTPException(status_code=422, detail="File too large (max 5 MB)")

    loc_id = await _resolve_location(db, user.tenant_id, location_id)

    try:
        items = parse_pushops_csv(file_bytes, fallback_pay_date=pay_date)
    except PushOpsParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    repo = ExpenseRepository(db)
    created = 0
    skipped = 0
    total = Decimal("0")
    pay_dates: set[str] = set()

    for item in items:
        vendor = f"Payroll — {item.employee}" if item.employee else "PushOperations Payroll"
        expense_dt = to_datetime(item.pay_date)
        if await repo.payroll_duplicate_exists(
            tenant_id=user.tenant_id,
            location_id=loc_id,
            expense_date=expense_dt,
            amount=item.amount,
            vendor_name=vendor,
        ):
            skipped += 1
            continue
        await repo.create_from_document(
            tenant_id=user.tenant_id,
            document_id=None,
            vendor_name=vendor,
            amount=item.amount,
            currency_code="CAD",
            location_id=loc_id,
            created_by=user.user_id,
            expense_date=expense_dt,
            category="Payroll",
            user_overridden=True,  # category is authoritative (payroll), never AI-recategorize
        )
        created += 1
        total += item.amount
        pay_dates.add(item.pay_date.isoformat())

    await AuditRepository(db).log(
        tenant_id=user.tenant_id,
        action="pushops.payroll_imported",
        user_id=user.user_id,
        entity_type="expense",
        entity_id=None,
        new_value={
            "filename": file.filename,
            "expenses_created": created,
            "duplicates_skipped": skipped,
            "total_amount": str(total),
        },
    )
    await db.commit()

    logger.info(
        "pushops_payroll_imported",
        tenant_id=str(user.tenant_id),
        location_id=str(loc_id) if loc_id else None,
        rows_parsed=len(items),
        created=created,
        skipped=skipped,
    )

    return {
        "data": PushOpsImportResult(
            rows_parsed=len(items),
            expenses_created=created,
            duplicates_skipped=skipped,
            total_amount=total,
            currency_code="CAD",
            pay_dates=sorted(pay_dates),
        ),
        "errors": None,
    }
