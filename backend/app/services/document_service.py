import hashlib
import uuid

import structlog

from app.core.exceptions import ConflictError, ValidationError
from app.db.models.document import ALLOWED_MIME_TYPES
from app.db.repositories.document_repo import DocumentRepository
from app.services.storage_service import upload_document

logger = structlog.get_logger(__name__)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

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
        from sqlalchemy import update as sa_update
        from app.db.models.document import Document
        await repo._db.execute(
            sa_update(Document)
            .where(Document.id == doc.id)
            .values(is_duplicate=True, duplicate_of=existing.id, status="error",
                    error_message="Duplicate of existing document")
        )
        logger.warning("document_duplicate", checksum=checksum, existing_id=str(existing.id))
        return doc, True

    # Enqueue OCR — non-fatal if Celery/Redis unavailable
    try:
        from app.workers.celery_app import celery_app
        celery_app.send_task(
            "app.workers.tasks.ocr_process.process_document",
            args=[str(doc.id), str(tenant_id)],
            queue="ocr",
        )
        logger.info("ocr_task_enqueued", document_id=str(doc.id))
    except Exception as e:
        logger.warning("ocr_task_enqueue_failed", document_id=str(doc.id), error=str(e))

    logger.info("document_ingested", document_id=str(doc.id), filename=original_filename)
    return doc, False