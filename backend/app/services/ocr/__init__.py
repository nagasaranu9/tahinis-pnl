from app.core.config import settings
from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult


def get_ocr_adapter() -> OCRAdapter:
    if settings.ANTHROPIC_API_KEY:
        from app.services.ocr.claude_adapter import ClaudeVisionAdapter
        return ClaudeVisionAdapter()
    if settings.GOOGLE_DOC_AI_PROCESSOR_ID:
        from app.services.ocr.google_adapter import GoogleDocumentAIAdapter
        return GoogleDocumentAIAdapter()
    from app.services.ocr.mock_adapter import MockOCRAdapter
    return MockOCRAdapter()


__all__ = ["OCRAdapter", "OCRLineItem", "OCRResult", "get_ocr_adapter"]
