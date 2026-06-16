import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    base=TrackedTask,
    bind=True,
    name="app.workers.tasks.ocr_process.process_document",
    queue="ocr",
    max_retries=3,
    default_retry_delay=60,
)
def process_document(self, document_id: str, tenant_id: str) -> dict:  # type: ignore[misc]
    """OCR process one document. Runs sync wrapper around async pipeline."""
    return asyncio.run(_process_async(document_id, tenant_id))


_PUSHOPERATIONS_KEYWORD = "pushoperations"


async def _pushoperations_integration_active(db, tenant_id: uuid.UUID) -> bool:
    from sqlalchemy import select
    from app.db.models.integration import IntegrationCredential

    row = (await db.execute(
        select(IntegrationCredential.id).where(
            IntegrationCredential.tenant_id == tenant_id,
            IntegrationCredential.provider == "pushoperations",
            IntegrationCredential.is_active == True,
        ).limit(1)
    )).scalar_one_or_none()
    return row is not None


async def _sync_pushoperations_payroll(
    db,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    location_id: uuid.UUID | None,
    expense_date: datetime,
    line_items: list,
    currency_code: str,
) -> None:
    """Pull payroll cost from bank statement line items when PushOperations
    isn't wired up as a live integration yet. Scans for PUSHOPERATIONS
    pre-authorized payment lines and books each as a Payroll expense, so
    Labor Cost in the P&L isn't stuck at zero just because Toast labor sync
    and the PushOperations integration are both empty."""
    matches = [
        li for li in line_items
        if li.description and _PUSHOPERATIONS_KEYWORD in li.description.lower()
    ]
    if not matches:
        return

    if await _pushoperations_integration_active(db, tenant_id):
        logger.info("pushoperations_bank_fallback_skipped_integration_active", tenant_id=str(tenant_id))
        return

    from app.db.repositories.expense_repo import ExpenseRepository
    expense_repo = ExpenseRepository(db)

    for li in matches:
        amount = abs(li.amount) if li.amount is not None else None
        if not amount:
            continue
        existing = await expense_repo.get_by_document_and_vendor(
            tenant_id=tenant_id, document_id=document_id, vendor_name="PushOperations Payroll"
        )
        if existing is not None:
            continue
        expense = await expense_repo.create_from_document(
            tenant_id=tenant_id,
            document_id=document_id,
            vendor_name="PushOperations Payroll",
            amount=amount,
            currency_code=currency_code,
            location_id=location_id,
            created_by=None,
            expense_date=expense_date,
        )
        # Categorize immediately — this is a rule match, not an AI guess, so
        # skip the categorize_expense AI dispatch entirely for this expense.
        expense.category = "Payroll"
        expense.is_ai_categorized = False
        await db.flush()
        logger.info(
            "pushoperations_bank_fallback_expense_created",
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            amount=str(amount),
        )


async def _process_async(document_id_str: str, tenant_id_str: str) -> dict:
    from app.db.repositories.document_repo import DocumentRepository
    from app.db.session import AsyncSessionLocal
    from app.services.ocr import get_ocr_adapter
    from app.services.storage_service import download_document

    doc_id = uuid.UUID(document_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async with AsyncSessionLocal() as db:
        repo = DocumentRepository(db)

        try:
            doc = await repo.get(tenant_id, doc_id)
        except Exception as exc:
            logger.error("ocr_doc_not_found", document_id=document_id_str, error=str(exc))
            return {"status": "error", "reason": "document_not_found"}

        await repo.update_status(doc_id, "ocr_processing")
        await db.commit()

        try:
            start_ms = int(datetime.now(UTC).timestamp() * 1000)
            file_bytes = download_document(doc.storage_path)

            adapter = get_ocr_adapter()
            result = await adapter.process(file_bytes, doc.mime_type)

            end_ms = int(datetime.now(UTC).timestamp() * 1000)
            result.processing_time_ms = end_ms - start_ms

            ocr_record = await repo.save_ocr_result(
                tenant_id=tenant_id,
                document_id=doc_id,
                provider=result.provider,
                raw_response=result.raw_response,
                extracted_text=result.extracted_text,
                confidence_score=result.confidence_score,
                page_count=result.page_count,
                processing_time_ms=result.processing_time_ms,
            )

            line_item_dicts = [
                {
                    "description": li.description,
                    "amount": li.amount,
                    "quantity": li.quantity,
                    "unit_price": li.unit_price,
                    "confidence_score": li.confidence_score,
                    "currency_code": result.currency_code,
                }
                for li in result.line_items
            ]
            await repo.save_line_items(tenant_id, doc_id, ocr_record.id, line_item_dicts)

            # Update document with extracted metadata
            doc_date = None
            if result.document_date:
                from datetime import date
                parsed = date.fromisoformat(result.document_date)
                doc_date = datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)

            # Bank-statement payroll fallback: if PushOperations isn't connected as
            # a live integration, pull labor cost straight from the bank statement
            # line items instead (PUSHOPERATIONS PAY/PAY pre-authorized payments are
            # the actual cash that left the account for payroll — more reliable than
            # an empty Toast labor sync). Runs for ANY document, not just ones already
            # classified bank_statement, since OCR classification can lag/misfire.
            await _sync_pushoperations_payroll(
                db,
                tenant_id=tenant_id,
                document_id=doc_id,
                location_id=doc.location_id,
                expense_date=doc_date or datetime.now(UTC),
                line_items=result.line_items,
                currency_code=result.currency_code or "CAD",
            )

            await repo.update_extracted_data(
                doc_id,
                vendor_name=result.vendor_name,
                document_date=doc_date,
                total_amount=result.total_amount,
                currency_code=result.currency_code,
                document_type="invoice",  # AI will refine in Phase 4
            )

            # Create Expense record from extracted document data (Phase 4)
            # Skip bank statements and reconciliation docs — not individual expenses
            _NON_EXPENSE_TYPES = {"bank_statement", "bank_reconciliation", "payroll_report", "other"}
            if doc.document_type in _NON_EXPENSE_TYPES:
                await db.commit()
                logger.info("ocr_skip_expense_for_type", document_type=doc.document_type)
                return {"status": "ok", "skipped_expense": True, "document_type": doc.document_type}

            from app.db.repositories.expense_repo import ExpenseRepository
            expense_repo = ExpenseRepository(db)
            existing = await expense_repo.get_by_document(tenant_id, doc_id)
            if existing is None:
                expense = await expense_repo.create_from_document(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    vendor_name=result.vendor_name,
                    amount=result.total_amount,
                    currency_code=result.currency_code or "CAD",
                    location_id=doc.location_id,
                    created_by=None,
                    expense_date=doc_date or datetime.now(UTC),
                )
                expense_id_for_ai = str(expense.id)
            elif existing.amount is None:
                # Backfill amount/vendor from real OCR only when the expense has no
                # real amount yet (e.g. a placeholder created before OCR ran). Never
                # overwrite a manually-entered expense — the user typed that amount
                # on purpose, OCR on the attached receipt is corroboration, not truth.
                if result.total_amount is not None or result.vendor_name:
                    await expense_repo.update_from_ocr(
                        tenant_id=tenant_id,
                        expense_id=existing.id,
                        amount=result.total_amount,
                        vendor_name=result.vendor_name,
                        currency_code=result.currency_code or "CAD",
                    )
                expense_id_for_ai = str(existing.id)
            else:
                expense_id_for_ai = str(existing.id)

            await db.commit()

            # Dispatch AI categorization after commit so expense row is visible
            from app.workers.tasks.ai_categorize import categorize_expense
            categorize_expense.apply_async(
                kwargs={"expense_id": expense_id_for_ai, "tenant_id": str(tenant_id)},
                queue="ai",
            )

            logger.info(
                "ocr_complete",
                document_id=document_id_str,
                vendor=result.vendor_name,
                total=str(result.total_amount),
                confidence=str(result.confidence_score),
                line_items=len(result.line_items),
            )
            return {"status": "success", "document_id": document_id_str}

        except Exception as exc:
            await repo.update_status(doc_id, "error", error_message=str(exc))
            await db.commit()
            logger.error("ocr_failed", document_id=document_id_str, error=str(exc))
            raise
