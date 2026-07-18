import hashlib
import uuid

import structlog

from app.core.exceptions import ConflictError, ValidationError
from app.db.models.document import ALLOWED_MIME_TYPES
from app.db.repositories.document_repo import DocumentRepository
from app.services.storage_service import upload_document

logger = structlog.get_logger(__name__)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Non-financial documents that arrive as email attachments (HR/ops noise, not
# invoices/receipts/bills). Skipped at ingest so they never hit OCR or the P&L.
_IGNORED_FILENAME_KEYWORDS = (
    "resume",
    "cv ",
    "cv_",
    "curriculum vitae",
    "memo",
    "checklist",
    "screenshot",
)


def is_ignored_filename(filename: str) -> bool:
    """True for clearly non-financial attachments (resumes, CVs, memos, etc.)."""
    name = filename.lower()
    return any(kw in name for kw in _IGNORED_FILENAME_KEYWORDS)

# Magic bytes for allowed types
_MAGIC_BYTES: dict[bytes, str] = {
    b"%PDF": "application/pdf",
    b"\x89PNG": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}


def validate_file(file_bytes: bytes, declared_mime_type: str, filename: str) -> str:
    """
    Validates MIME type (whitelist + magic bytes) and size.
    Returns confirmed mime_type. Raises ValidationError on failure.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValidationError(f"File exceeds 50MB limit ({len(file_bytes)} bytes)")

    if declared_mime_type not in ALLOWED_MIME_TYPES:
        raise ValidationError(
            f"File type '{declared_mime_type}' not allowed. Allowed: pdf, png, jpg, jpeg, tiff"
        )

    # Magic byte check — detect MIME from actual bytes
    detected: str | None = None
    for magic, mime in _MAGIC_BYTES.items():
        if file_bytes[: len(magic)] == magic:
            detected = mime
            break

    if detected is None:
        raise ValidationError(f"File '{filename}' failed magic byte validation. Content type not recognized.")

    if detected != declared_mime_type:
        raise ValidationError(
            f"File content ({detected}) does not match declared type ({declared_mime_type}). Rejecting."
        )

    return detected


async def ingest_document(
    file_bytes: bytes,
    original_filename: str,
    mime_type: str,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
    repo: DocumentRepository,
    location_id: uuid.UUID | None = None,
    source: str = "manual_upload",
) -> tuple:
    """
    Full ingest pipeline:
    1. Validate
    2. Check duplicate
    3. Upload to storage
    4. Create DB record
    5. Enqueue OCR task
    Returns (document, is_new_duplicate)
    """
    # Auto-synced (email/drive) attachments get the non-financial filter; a manual
    # upload is a deliberate user choice and is never silently dropped.
    if not source.startswith("manual") and is_ignored_filename(original_filename):
        logger.info("document_ignored_non_financial", filename=original_filename, source=source)
        return None, False

    confirmed_mime = validate_file(file_bytes, mime_type, original_filename)
    checksum = hashlib.sha256(file_bytes).hexdigest()

    # Duplicate detection by checksum
    existing = await repo.find_duplicate(tenant_id, checksum)

    storage_path, _ = upload_document(file_bytes, tenant_id, original_filename, confirmed_mime)

    doc = await repo.create(
        tenant_id=tenant_id,
        created_by=created_by,
        original_filename=original_filename,
        storage_path=storage_path,
        mime_type=confirmed_mime,
        file_size_bytes=len(file_bytes),
        checksum_sha256=checksum,
        source=source,
        location_id=location_id,
    )

    if existing is not None:
        # Set attributes on the live ORM object rather than issuing a raw
        # UPDATE against the same row — a Core UPDATE against a mapped table
        # expires the matching identity-map object's attributes, and the
        # caller's subsequent DocumentResponse.model_validate(doc) then
        # triggers a lazy-reload outside an async-safe context
        # (MissingGreenlet), crashing the upload endpoint with a 500 on
        # every duplicate upload.
        doc.is_duplicate = True
        doc.duplicate_of = existing.id
        doc.status = "error"
        doc.error_message = "Duplicate of existing document"
        await repo._db.flush()
        logger.warning("document_duplicate", checksum=checksum, existing_id=str(existing.id))
        return doc, True

    # Enqueue OCR — non-fatal if Redis unavailable (v3)
    logger.info("ocr_enqueue_attempt_v3", document_id=str(doc.id))
    try:
        from app.workers.tasks.ocr_process import process_document
        process_document.delay(str(doc.id), str(tenant_id))
        logger.info("ocr_task_enqueued", document_id=str(doc.id))
    except Exception as e:
        logger.warning("ocr_task_enqueue_failed_v3", document_id=str(doc.id), error=str(e), error_type=type(e).__name__)

    logger.info("document_ingested", document_id=str(doc.id), filename=original_filename)
    return doc, False