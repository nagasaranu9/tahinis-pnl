import structlog

from app.services.ocr.base import OCRAdapter, OCRResult

logger = structlog.get_logger()


class AutoOCRAdapter(OCRAdapter):
    """Tries `primary` first; on any failure, falls back to `secondary`.

    Used for OCR_ADAPTER=auto / tenant ocr_preferred_provider=auto: Google
    Document AI is cheap and configured, but if it errors (quota, bad creds,
    processor down) or isn't configured at all, Claude Vision covers the doc
    instead of leaving it stuck in "error".
    """

    def __init__(self, primary: OCRAdapter, secondary: OCRAdapter) -> None:
        self._primary = primary
        self._secondary = secondary

    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        try:
            return await self._primary.process(file_bytes, mime_type)
        except Exception as exc:
            logger.warning(
                "ocr_primary_failed_falling_back",
                primary=type(self._primary).__name__,
                secondary=type(self._secondary).__name__,
                error=str(exc),
            )
            return await self._secondary.process(file_bytes, mime_type)
