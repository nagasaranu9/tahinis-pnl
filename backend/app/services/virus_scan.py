"""
Virus scanning for uploaded files.

Strategy:
1. Always validate file magic bytes against declared MIME type (prevents spoofing).
2. If CLAMAV_HOST is configured, scan via clamd TCP socket.
   If not configured (dev/test), skip AV scan but still validate magic bytes.

Raises VirusScanError if infected or scan fails in strict mode.
"""
from __future__ import annotations

import socket
import struct
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Mapping: mime_type → accepted magic byte prefixes
_MAGIC: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/png": [b"\x89PNG"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/tiff": [b"II*\x00", b"MM\x00*"],
}

ALLOWED_MIME_TYPES = set(_MAGIC.keys())


class VirusScanError(Exception):
    """Raised when a file fails virus scan or MIME validation."""


def validate_mime(file_bytes: bytes, declared_mime: str) -> None:
    """Validate file magic bytes match declared MIME type."""
    prefixes = _MAGIC.get(declared_mime)
    if prefixes is None:
        # Unsupported MIME — block it
        raise VirusScanError(f"Unsupported file type: {declared_mime}")
    if not any(file_bytes.startswith(p) for p in prefixes):
        raise VirusScanError(
            f"File content does not match declared MIME type: {declared_mime}"
        )


def scan_with_clamav(file_bytes: bytes, filename: str) -> None:
    """
    Stream file to ClamAV daemon via INSTREAM command.
    Raises VirusScanError if infected or connection fails.
    """
    host = getattr(settings, "CLAMAV_HOST", "") or ""
    port = int(getattr(settings, "CLAMAV_PORT", 3310))

    if not host:
        logger.debug("clamav_skipped_no_host", filename=filename)
        return

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((host, port))

        # INSTREAM protocol: send "zINSTREAM\0", then chunks (4-byte big-endian length + data), then 0-length chunk
        sock.sendall(b"zINSTREAM\0")

        chunk_size = 4096
        for i in range(0, len(file_bytes), chunk_size):
            chunk = file_bytes[i : i + chunk_size]
            sock.sendall(struct.pack(">I", len(chunk)) + chunk)
        sock.sendall(struct.pack(">I", 0))  # end of stream

        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            if b"\0" in data or len(response) > 1024:
                break

        sock.close()
        result = response.rstrip(b"\0").decode("utf-8", errors="replace")
        logger.info("clamav_scan_result", filename=filename, result=result)

        if "FOUND" in result:
            # Extract threat name from "stream: Virus.Name FOUND"
            threat = result.split(":")[1].strip().split(" FOUND")[0].strip() if ":" in result else "unknown"
            raise VirusScanError(f"Malware detected: {threat}")

        if "ERROR" in result:
            raise VirusScanError(f"ClamAV scan error: {result}")

    except VirusScanError:
        raise
    except Exception as exc:
        # ClamAV unavailable — fail open (log + continue) unless strict mode
        strict = bool(getattr(settings, "CLAMAV_STRICT", False))
        logger.error("clamav_connection_failed", filename=filename, error=str(exc), strict=strict)
        if strict:
            raise VirusScanError(f"Virus scan unavailable: {exc}") from exc


def scan_upload(file_bytes: bytes, filename: str, declared_mime: str) -> None:
    """
    Full upload scan pipeline:
    1. MIME magic byte validation
    2. ClamAV AV scan (if configured)

    Raises VirusScanError on failure.
    """
    validate_mime(file_bytes, declared_mime)
    scan_with_clamav(file_bytes, filename)
    logger.info("upload_scan_passed", filename=filename, mime=declared_mime, size=len(file_bytes))
