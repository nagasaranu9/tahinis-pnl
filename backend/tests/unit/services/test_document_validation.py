import pytest

from app.core.exceptions import ValidationError
from app.services.document_service import MAX_FILE_SIZE_BYTES, validate_file

# Valid magic bytes
PDF_HEADER = b"%PDF-1.4 fake content"
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 100


def test_valid_pdf() -> None:
    mime = validate_file(PDF_HEADER, "application/pdf", "invoice.pdf")
    assert mime == "application/pdf"


def test_valid_png() -> None:
    mime = validate_file(PNG_HEADER, "image/png", "receipt.png")
    assert mime == "image/png"


def test_valid_jpeg() -> None:
    mime = validate_file(JPEG_HEADER, "image/jpeg", "photo.jpg")
    assert mime == "image/jpeg"


def test_rejects_disallowed_mime() -> None:
    with pytest.raises(ValidationError, match="not allowed"):
        validate_file(PDF_HEADER, "application/zip", "archive.zip")


def test_rejects_oversized_file() -> None:
    large = b"A" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(ValidationError, match="50MB"):
        validate_file(large, "application/pdf", "huge.pdf")


def test_rejects_mime_mismatch() -> None:
    # PNG bytes but declared as PDF
    with pytest.raises(ValidationError, match="does not match"):
        validate_file(PNG_HEADER, "application/pdf", "fake.pdf")


def test_rejects_unknown_magic_bytes() -> None:
    garbage = b"\x00\x01\x02\x03garbage content"
    with pytest.raises(ValidationError, match="magic byte"):
        validate_file(garbage, "application/pdf", "bad.pdf")
