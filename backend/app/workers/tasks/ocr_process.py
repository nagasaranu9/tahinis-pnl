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


# ---------------------------------------------------------------------------
# Bank statement expense extraction helpers
# ---------------------------------------------------------------------------

_DEBIT_SIGNALS = (
    "pad", "pap", "payment", "debit", "purchase", "withdrawal",
    "pre-authorized", "preauthorized", "chq", "cheque", "pos ",
    "visa debit", "interac", "e-transfer out", "wire out",
)
_CREDIT_SIGNALS = (
    "deposit", "credit", "interest earned", "payroll deposit",
    "transfer in", "etransfer in", "e-transfer in", "refund",
    "payroll credit", "direct deposit",
)
_SKIP_VENDOR_NOISE = (
    "nsf", "service charge", "monthly fee", "overdraft fee",
    "bank fee", "account fee", "wire fee",
)

# Hard non-expense exclusions for bank statements. These are NOT operating
# expenses and must never hit the P&L — counting them double-counts or inflates
# opex (a restaurant's real costs are the underlying purchases, not the cash
# movements that settle them):
#   - account transfers (money moved between own accounts)
#   - credit-card bill payments (the itemized purchases are the expense, not the
#     payment that clears the card balance)
#   - "payments and credits" summary lines (these are inflows, not outflows)
#   - loan principal repayments (balance-sheet, not P&L; interest IS an expense
#     and is caught separately by the Professional Services keyword map)
_NON_EXPENSE_BANK_KEYWORDS = (
    "trsf", "transfer", "tfr ", "tfr-", "e-transfer", "etransfer",
    "online bill payment", "bill payment, amex", "bill payment, visa",
    "bill payment, mastercard", "credit card payment", "cc payment",
    "card payment", "amex", "mastercard payment", "visa payment",
    "payments and credits", "payment and credit",
    "loan payment", "loan principal", "mortgage principal",
    "internal transfer", "own account", "account to account",
)


def _is_non_expense_bank_line(description: str) -> bool:
    """True when a bank line is a transfer / card-bill payment / credit summary —
    movements that must be excluded from the P&L."""
    desc = description.lower()
    return any(k in desc for k in _NON_EXPENSE_BANK_KEYWORDS)


def _is_debit_line(description: str, amount: "Decimal") -> bool:
    desc = description.lower()
    if amount < 0:
        return True
    if any(k in desc for k in _CREDIT_SIGNALS):
        return False
    if any(k in desc for k in _DEBIT_SIGNALS):
        return True
    return False


def _vendor_from_description(description: str) -> str:
    import re
    cleaned = re.sub(r'\s+\d{4,}.*$', '', description)
    cleaned = re.sub(r'\s+\d{2}/\d{2}.*$', '', cleaned)
    cleaned = re.sub(r'\s+(pad|pap|debit|credit|chq)\b.*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned[:100] if cleaned else description[:100]


async def _gmail_verify_expense(
    db,
    tenant_id: "uuid.UUID",
    vendor_name: str,
    amount: "Decimal",
    doc_date: "datetime",
) -> tuple[bool, str]:
    """Look for a matching invoice/bill in Gmail email_messages and linked documents."""
    from datetime import timedelta
    from decimal import Decimal as _D
    from sqlalchemy import select, or_
    from app.db.models.email_sync import EmailMessage
    from app.db.models.document import Document

    vendor_token = " ".join(vendor_name.split()[:3]).lower()
    date_low = doc_date - timedelta(days=30)
    date_high = doc_date + timedelta(days=7)

    # 1. Matching email sender/subject
    try:
        row = (await db.execute(
            select(EmailMessage.sender, EmailMessage.subject, EmailMessage.received_at)
            .where(
                EmailMessage.tenant_id == tenant_id,
                EmailMessage.received_at.between(date_low, date_high),
                or_(
                    EmailMessage.sender.ilike(f"%{vendor_token}%"),
                    EmailMessage.subject.ilike(f"%{vendor_token}%"),
                ),
            )
            .limit(1)
        )).first()
        if row:
            return True, f"Gmail match: {row.sender or row.subject}"
    except Exception:
        pass

    # 2. Email-sourced document matching vendor + amount ±10%
    try:
        tol = abs(amount) * _D("0.10")
        doc_row = (await db.execute(
            select(Document.vendor_name, Document.total_amount)
            .where(
                Document.tenant_id == tenant_id,
                Document.source.in_(("email_gmail", "email_outlook")),
                Document.vendor_name.ilike(f"%{vendor_token}%"),
                Document.total_amount.between(abs(amount) - tol, abs(amount) + tol),
                Document.document_date.between(date_low, date_high),
            )
            .limit(1)
        )).first()
        if doc_row:
            return True, f"Email invoice: {doc_row.vendor_name} ${doc_row.total_amount}"
    except Exception:
        pass

    return False, "No matching Gmail invoice found"


async def _parse_bank_transactions_with_claude(extracted_text: str, currency_code: str) -> list[dict]:
    """Extract debit transactions from raw bank statement OCR text via Claude haiku.
    Google Invoice Parser returns no line_items for bank statements — this is the fallback.
    Returns list of {description, amount (positive Decimal), date (str|None)}."""
    import json
    from decimal import Decimal, InvalidOperation
    import anthropic
    from app.core.config import settings

    if not extracted_text or len(extracted_text) < 50:
        return []

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    text_sample = extracted_text[:5000]

    prompt = (
        "Extract all debit/withdrawal transactions from this bank statement text.\n"
        "Return ONLY a JSON array. Each element: "
        '{"description": "vendor name", "amount": 123.45, "date": "2026-05-15"}\n'
        "Rules:\n"
        "- amount: positive number (the withdrawal/debit amount)\n"
        "- Skip deposits, credits, interest earned, transfers in, refunds\n"
        "- Skip opening/closing balance lines\n"
        "- Skip NSF fees, bank service charges, monthly fees\n"
        "- Skip account transfers (TRSF, TFR, transfer between accounts)\n"
        "- Skip credit-card bill payments (Online Bill Payment to AMEX/VISA/Mastercard)\n"
        "- Skip 'payments and credits' summary lines and loan principal repayments\n"
        "- Return [] if no debit transactions found\n\n"
        f"Bank statement text:\n{text_sample}\n\n"
        "JSON array only, no prose:"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        result = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            desc = str(item.get("description", "")).strip()
            if not desc:
                continue
            try:
                amount = Decimal(str(item.get("amount", 0))).quantize(Decimal("0.01"))
            except InvalidOperation:
                continue
            if amount <= 0:
                continue
            result.append({
                "description": desc,
                "amount": amount,
                "date": item.get("date"),
            })
        logger.info("bank_statement_claude_parsed", transactions=len(result))
        return result
    except Exception as exc:
        logger.warning("bank_statement_claude_parse_failed", error=str(exc))
        return []


async def _extract_bank_statement_expenses(
    db,
    tenant_id: "uuid.UUID",
    document_id: "uuid.UUID",
    location_id: "uuid.UUID | None",
    doc_date: "datetime",
    line_items: list,
    currency_code: str,
    extracted_text: str = "",
) -> int:
    """Parse debit transactions from a bank statement and create Expense rows.

    Google Invoice Parser returns empty line_items for bank statements — falls back
    to Claude haiku text parsing of the raw OCR text. Returns count created."""
    from decimal import Decimal
    from app.db.repositories.expense_repo import ExpenseRepository
    from app.workers.tasks.ai_categorize import categorize_expense

    expense_repo = ExpenseRepository(db)
    created = 0

    # Build unified transaction list. Invoice Parser populates line_items for invoices
    # but returns nothing for bank statements — use Claude text parsing as fallback.
    transactions: list[dict] = []
    if line_items:
        for li in line_items:
            if not li.description:
                continue
            desc_lower = li.description.lower()
            if any(k in desc_lower for k in _SKIP_VENDOR_NOISE):
                continue
            if _is_non_expense_bank_line(li.description):
                continue
            if li.amount is None or not _is_debit_line(li.description, li.amount):
                continue
            transactions.append({
                "description": li.description,
                "amount": abs(li.amount),
                "date": None,
            })

    if not transactions and extracted_text:
        transactions = await _parse_bank_transactions_with_claude(extracted_text, currency_code)

    for tx in transactions:
        desc = tx["description"]
        amount: "Decimal" = tx["amount"]
        if not amount or amount <= 0:
            continue

        desc_lower = desc.lower()
        if any(k in desc_lower for k in _SKIP_VENDOR_NOISE):
            continue
        if _is_non_expense_bank_line(desc):
            continue

        # Use per-transaction date when Claude extracted it; fall back to statement date.
        tx_date = doc_date
        if tx.get("date"):
            try:
                from datetime import date as _date
                parsed = _date.fromisoformat(str(tx["date"]))
                tx_date = datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)
            except Exception:
                pass

        vendor = _vendor_from_description(desc)

        if await expense_repo.get_by_document_and_vendor(
            tenant_id=tenant_id, document_id=document_id, vendor_name=vendor
        ) is not None:
            continue

        gmail_verified, gmail_note = await _gmail_verify_expense(
            db, tenant_id, vendor, amount, tx_date
        )

        expense = await expense_repo.create_from_document(
            tenant_id=tenant_id,
            document_id=document_id,
            vendor_name=vendor,
            amount=amount,
            currency_code=currency_code,
            location_id=location_id,
            created_by=None,
            expense_date=tx_date,
        )
        expense.ai_explanation = (
            f"Bank statement import. Gmail verified: {'Yes' if gmail_verified else 'No'}. "
            f"{gmail_note}. Raw: {desc[:150]}"
        )
        expense.is_ai_categorized = False
        await db.flush()

        categorize_expense.apply_async(
            kwargs={"expense_id": str(expense.id), "tenant_id": str(tenant_id)},
            queue="ai",
        )
        logger.info(
            "bank_expense_created",
            tenant_id=str(tenant_id),
            vendor=vendor,
            amount=str(amount),
            gmail_verified=gmail_verified,
        )
        created += 1

    return created


_BANK_STATEMENT_KEYWORDS = (
    "bank statement", "account statement", "statement of account",
    "bmo", "td bank", "rbc", "scotiabank", "cibc", "desjardins",
    "national bank", "hsbc", "tangerine", "simplii",
    "daily balance", "opening balance", "closing balance",
    "deposits", "withdrawals", "cheques",
)
_BANK_STATEMENT_FILENAME_KEYWORDS = (
    "statement", "bank", "bmo", "td", "rbc", "scotiabank",
)
_RECEIPT_KEYWORDS = ("receipt", "thank you for your purchase", "subtotal", "tax", "change due")
_INVOICE_KEYWORDS = ("invoice", "bill to", "invoice #", "invoice number", "due date", "payment terms")
_PAYROLL_KEYWORDS = ("payroll", "pay stub", "pay slip", "earnings statement", "pushoperations", "payslip")


def _classify_document_type(
    filename: str | None,
    vendor_name: str | None,
    extracted_text: str | None,
) -> str:
    """Heuristic document classifier. Returns a document_type string."""
    name_lower = (filename or "").lower()
    vendor_lower = (vendor_name or "").lower()
    text_lower = (extracted_text or "")[:3000].lower()

    combined = f"{name_lower} {vendor_lower} {text_lower}"

    _BANK_VENDOR_KEYWORDS = (
        "bank", "bmo", "td", "rbc", "scotiabank", "cibc", "desjardins",
        "hsbc", "tangerine", "simplii", "national bank", "montreal",
    )
    vendor_is_bank = any(k in vendor_lower for k in _BANK_VENDOR_KEYWORDS)
    filename_is_bank = any(k in name_lower for k in _BANK_STATEMENT_FILENAME_KEYWORDS)
    text_bank_hits = sum(1 for k in _BANK_STATEMENT_KEYWORDS if k in combined)

    # Bank statement detection FIRST — a bank statement can contain a
    # PUSHOPERATIONS payroll debit line, which must NOT cause it to be
    # classified as a payroll_report. The vendor being a bank (e.g. "BMO Bank
    # of Montreal", which Document AI returns as supplier_name on a statement)
    # is the strongest signal.
    if vendor_is_bank:
        return "bank_statement"
    if filename_is_bank and text_bank_hits >= 1:
        return "bank_statement"
    if text_bank_hits >= 2:
        return "bank_statement"

    # Payroll report = an actual pay stub / earnings statement (not a bank
    # statement that merely lists a payroll withdrawal).
    if any(k in combined for k in _PAYROLL_KEYWORDS):
        return "payroll_report"

    if any(k in combined for k in _RECEIPT_KEYWORDS):
        return "receipt"

    if any(k in combined for k in _INVOICE_KEYWORDS):
        return "invoice"

    return "invoice"  # safe default — creates expense, user can reclassify


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

            classified_type = _classify_document_type(
                filename=doc.original_filename,
                vendor_name=result.vendor_name,
                extracted_text=result.extracted_text,
            )

            await repo.update_extracted_data(
                doc_id,
                vendor_name=result.vendor_name,
                document_date=doc_date,
                total_amount=result.total_amount,
                currency_code=result.currency_code,
                document_type=classified_type,
            )

            # Bank statements: extract individual debit transactions as expenses
            # and Gmail-verify each one. PushOps payroll fallback already ran above.
            if classified_type == "bank_statement":
                bank_created = await _extract_bank_statement_expenses(
                    db,
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    location_id=doc.location_id,
                    doc_date=doc_date or datetime.now(UTC),
                    line_items=result.line_items,
                    currency_code=result.currency_code or "CAD",
                    extracted_text=result.extracted_text or "",
                )
                await db.commit()
                logger.info(
                    "bank_statement_expenses_extracted",
                    document_id=document_id_str,
                    bank_expenses_created=bank_created,
                )
                return {
                    "status": "ok",
                    "document_type": "bank_statement",
                    "bank_expenses_created": bank_created,
                }

            # Skip other non-expense document types
            _NON_EXPENSE_TYPES = {"bank_reconciliation", "payroll_report", "other"}
            if classified_type in _NON_EXPENSE_TYPES:
                await db.commit()
                logger.info("ocr_skip_expense_for_type", document_type=classified_type)
                return {"status": "ok", "skipped_expense": True, "document_type": classified_type}

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
