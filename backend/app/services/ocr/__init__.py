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
    if choice == "tesseract":
        from app.services.ocr.tesseract_adapter import TesseractAdapter
        return TesseractAdapter()
    if choice == "mock":
        from app.services.ocr.mock_adapter import MockOCRAdapter
        return MockOCRAdapter()

    # auto: Google primary + Claude fallback when both are configured;
    # otherwise whichever one is configured; otherwise mock.
    if google_configured and claude_configured:
        from app.services.ocr.auto_adapter import AutoOCRAdapter
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return AutoOCRAdapter(primary=GoogleDocumentAIAdapter(), secondary=ClaudeVisionAdapter())
    if google_configured:
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return GoogleDocumentAIAdapter()
    if claude_configured:
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        return ClaudeVisionAdapter()
    from app.services.ocr.mock_adapter import MockOCRAdapter
    return MockOCRAdapter()


__all__ = ["OCRAdapter", "OCRLineItem", "OCRResult", "get_ocr_adapter"]
