import asyncio
import uuid

import structlog

from app.workers.base_task import TrackedTask
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    base=TrackedTask,
    bind=True,
    name="app.workers.tasks.ai_categorize.categorize_expense",
    queue="ai",
    max_retries=3,
    default_retry_delay=30,
)
def categorize_expense(self, expense_id: str, tenant_id: str) -> dict:  # type: ignore[misc]
    return asyncio.run(_categorize_async(expense_id, tenant_id))


async def _categorize_async(expense_id_str: str, tenant_id_str: str) -> dict:
    from app.db.repositories.expense_repo import ExpenseRepository
    from app.db.repositories.document_repo import DocumentRepository
    from app.db.session import AsyncSessionLocal
    from app.services.ai.categorization_service import CategorizationService

    expense_id = uuid.UUID(expense_id_str)
    tenant_id = uuid.UUID(tenant_id_str)

    async with AsyncSessionLocal() as db:
        expense_repo = ExpenseRepository(db)
        doc_repo = DocumentRepository(db)

        try:
            expense = await expense_repo.get(tenant_id, expense_id)
        except Exception as exc:
            logger.error("ai_categorize_expense_not_found", expense_id=expense_id_str, error=str(exc))
            return {"status": "error", "reason": "expense_not_found"}

        # Fetch line item descriptions from the linked document
        line_item_descriptions: list[str] = []
        document_type: str | None = None
        if expense.document_id:
            try:
                doc = await doc_repo.get(tenant_id, expense.document_id)
                document_type = doc.document_type
                # For bank statements, each expense is ONE transaction — its vendor
                # name is the only relevant signal. Passing the document's full line
                # items (every transaction on the statement) poisons categorization:
                # the haystack then contains "pushoperations"/"payroll" for EVERY row,
                # so the keyword map buckets everything into Payroll. Only pass line
                # items for invoices/receipts where they describe that one purchase.
                if document_type != "bank_statement":
                    items = await doc_repo.get_line_items(expense.document_id)
                    line_item_descriptions = [i.description for i in items if i.description]
            except Exception:
                pass

        svc = CategorizationService()
        result = await svc.categorize(
            vendor_name=expense.vendor_name,
            amount=expense.amount,
            currency_code=expense.currency_code,
            document_type=document_type,
            line_item_descriptions=line_item_descriptions,
        )

        await expense_repo.apply_ai_categorization(
            expense_id=expense_id,
            ai_suggested_category=result.category,
            ai_confidence_score=result.confidence,
            ai_explanation=result.explanation,
        )
        await db.commit()

        logger.info(
            "ai_categorize_complete",
            expense_id=expense_id_str,
            category=result.category,
            confidence=str(result.confidence),
        )
        return {
            "status": "success",
            "expense_id": expense_id_str,
            "category": result.category,
            "confidence": str(result.confidence),
        }
