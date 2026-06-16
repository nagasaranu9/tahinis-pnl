"""Unit tests for virus_scan service."""
import pytest
from unittest.mock import patch, MagicMock
import socket
import struct

from app.services.virus_scan import (
    validate_mime,
    scan_upload,
    scan_with_clamav,
    VirusScanError,
    ALLOWED_MIME_TYPES,
)

# Valid magic byte samples
PDF_BYTES = b"%PDF-1.4 fake content"
PNG_BYTES = b"\x89PNG\r\n\x1a\n fake content"
JPEG_BYTES = b"\xff\xd8\xff\xe0 fake content"
TIFF_LE_BYTES = b"II*\x00 fake content"
TIFF_BE_BYTES = b"MM\x00* fake content"


class TestValidateMime:
    def test_pdf_valid(self):
        validate_mime(PDF_BYTES, "application/pdf")  # no raise

    def test_png_valid(self):
        validate_mime(PNG_BYTES, "image/png")

    def test_jpeg_valid(self):
        validate_mime(JPEG_BYTES, "image/jpeg")

    def test_tiff_little_endian_valid(self):
        validate_mime(TIFF_LE_BYTES, "image/tiff")

    def test_tiff_big_endian_valid(self):
        validate_mime(TIFF_BE_BYTES, "image/tiff")

    def test_pdf_bytes_wrong_mime_rejected(self):
        with pytest.raises(VirusScanError, match="does not match"):
            validate_mime(PDF_BYTES, "image/png")

    def test_unsupported_mime_rejected(self):
        with pytest.raises(VirusScanError, match="Unsupported"):
            validate_mime(b"anything", "application/exe")

    def test_all_allowed_mimes_have_magic(self):
        """Every ALLOWED_MIME_TYPE must have magic bytes defined."""
        from app.services.virus_scan import _MAGIC
        for mime in ALLOWED_MIME_TYPES:
            assert mime in _MAGIC


class TestScanWithClamav:
    def test_skipped_when_no_host(self):
        """No CLAMAV_HOST → scan skipped silently."""
        with patch("app.services.virus_scan.settings") as mock_settings:
            mock_settings.CLAMAV_HOST = ""
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = False
            scan_with_clamav(PDF_BYTES, "test.pdf")  # no raise

    def test_clean_file_passes(self):
        """ClamAV returns 'stream: OK' → no error."""
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"stream: OK\0", b""]

        with patch("app.services.virus_scan.settings") as mock_settings, \
             patch("socket.socket") as mock_socket_cls:
            mock_settings.CLAMAV_HOST = "clamav"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = False
            mock_socket_cls.return_value = mock_sock

            scan_with_clamav(PDF_BYTES, "clean.pdf")  # no raise

    def test_infected_file_raises(self):
        """ClamAV returns FOUND → VirusScanError."""
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [b"stream: Eicar-Test-Signature FOUND\0", b""]

        with patch("app.services.virus_scan.settings") as mock_settings, \
             patch("socket.socket") as mock_socket_cls:
            mock_settings.CLAMAV_HOST = "clamav"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = False
            mock_socket_cls.return_value = mock_sock

            with pytest.raises(VirusScanError, match="Malware detected"):
                scan_with_clamav(PDF_BYTES, "infected.pdf")

    def test_connection_failure_strict_raises(self):
        """Connection failure + CLAMAV_STRICT=True → VirusScanError."""
        with patch("app.services.virus_scan.settings") as mock_settings, \
             patch("socket.socket") as mock_socket_cls:
            mock_settings.CLAMAV_HOST = "clamav"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = True
            mock_socket_cls.return_value = MagicMock()
            mock_socket_cls.return_value.connect.side_effect = ConnectionRefusedError("refused")

            with pytest.raises(VirusScanError, match="unavailable"):
                scan_with_clamav(PDF_BYTES, "test.pdf")

    def test_connection_failure_non_strict_passes(self):
        """Connection failure + CLAMAV_STRICT=False → fail open (no error)."""
        with patch("app.services.virus_scan.settings") as mock_settings, \
             patch("socket.socket") as mock_socket_cls:
            mock_settings.CLAMAV_HOST = "clamav"
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = False
            mock_socket_cls.return_value = MagicMock()
            mock_socket_cls.return_value.connect.side_effect = ConnectionRefusedError("refused")

            scan_with_clamav(PDF_BYTES, "test.pdf")  # no raise


class TestScanUpload:
    def test_full_pipeline_clean(self):
        with patch("app.services.virus_scan.settings") as mock_settings:
            mock_settings.CLAMAV_HOST = ""
            mock_settings.CLAMAV_PORT = 3310
            mock_settings.CLAMAV_STRICT = False
            scan_upload(PDF_BYTES, "invoice.pdf", "application/pdf")  # no raise

    def test_full_pipeline_wrong_mime_rejected(self):
        with patch("app.services.virus_scan.settings") as mock_settings:
            mock_settings.CLAMAV_HOST = ""
            scan_upload_kwargs = dict(
                file_bytes=PNG_BYTES,
                filename="tricky.pdf",
                declared_mime="application/pdf",
            )
            with pytest.raises(VirusScanError):
                scan_upload(**scan_upload_kwargs)
