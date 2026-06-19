from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult


def get_ocr_adapter() -> OCRAdapter:
    """Select OCR adapter.

    Controlled by settings.OCR_ADAPTER:
      - "auto" (default): Google Document AI if a processor is configured (cheap,
        ~$1.50/1k pages), else Claude Vision, else Tesseract (free), else mock.
        Prefers Google over Claude to avoid burning Anthropic credits.
      - "google" / "claude" / "tesseract" / "mock": force a specific adapter.
    """
    choice = (settings.OCR_ADAPTER or "auto").lower()

    if choice == "google":
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return GoogleDocumentAIAdapter()
    if choice == "claude":
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        return ClaudeVisionAdapter()
    if choice == "tesseract":
        from app.services.ocr.tesseract_adapter import TesseractAdapter
        return TesseractAdapter()
    if choice == "mock":
        from app.services.ocr.mock_adapter import MockOCRAdapter
        return MockOCRAdapter()

    # auto: cheapest capable adapter that's configured
    if settings.GOOGLE_DOC_AI_PROCESSOR_ID:
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return GoogleDocumentAIAdapter()
    if settings.ANTHROPIC_API_KEY:
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        return ClaudeVisionAdapter()
    from app.services.ocr.mock_adapter import MockOCRAdapter
    return MockOCRAdapter()


__all__ = ["OCRAdapter", "OCRLineItem", "OCRResult", "get_ocr_adapter"]
