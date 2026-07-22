from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult


def get_ocr_adapter(tenant_preferred_provider: str | None = None) -> OCRAdapter:
    """Select OCR adapter.

    `tenant_preferred_provider` (Tenant.ocr_preferred_provider — "auto" / "google"
    / "claude") overrides the global settings.OCR_ADAPTER default when given:
      - "auto": Google Document AI primary, Claude Vision fallback on failure
        (via AutoOCRAdapter). If Google isn't configured, Claude runs directly.
      - "google" / "claude": force a specific adapter, no fallback.
      - unset: falls back to settings.OCR_ADAPTER, same semantics, plus
        "tesseract" / "mock" for local dev/testing.
    """
    choice = (tenant_preferred_provider or settings.OCR_ADAPTER or "auto").lower()
    google_configured = bool(settings.GOOGLE_DOC_AI_PROCESSOR_ID)
    claude_configured = bool(settings.ANTHROPIC_API_KEY)

    if choice == "google":
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return GoogleDocumentAIAdapter()
    if choice == "claude":
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        return ClaudeVisionAdapter()
    if choice == "markitdown":
        from app.services.ocr.markitdown_adapter import MarkItDownAdapter
        return MarkItDownAdapter()
    if choice == "tesseract":
        from app.services.ocr.tesseract_adapter import TesseractAdapter
        return TesseractAdapter()
    if choice == "mock":
        from app.services.ocr.mock_adapter import MockOCRAdapter
        return MockOCRAdapter()

    # auto: cheapest-capable-first chain with fallback on failure.
    # markitdown (native-text extract, cheap) -> Google Doc AI -> Claude Vision.
    # markitdown needs an Anthropic key to structure the extracted text; it
    # raises on scanned/image PDFs so the next engine handles them.
    from app.services.ocr.auto_adapter import AutoOCRAdapter

    tail: OCRAdapter | None = None
    if google_configured and claude_configured:
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        tail = AutoOCRAdapter(primary=GoogleDocumentAIAdapter(), secondary=ClaudeVisionAdapter())
    elif google_configured:
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        tail = GoogleDocumentAIAdapter()
    elif claude_configured:
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        tail = ClaudeVisionAdapter()

    if claude_configured and tail is not None:
        from app.services.ocr.markitdown_adapter import MarkItDownAdapter
        return AutoOCRAdapter(primary=MarkItDownAdapter(), secondary=tail)
    if tail is not None:
        return tail
    from app.services.ocr.mock_adapter import MockOCRAdapter
    return MockOCRAdapter()


__all__ = ["OCRAdapter", "OCRLineItem", "OCRResult", "get_ocr_adapter"]
