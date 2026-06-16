from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class OCRLineItem:
    description: str
    amount: Decimal
    confidence_score: Decimal
    quantity: Decimal | None = None
    unit_price: Decimal | None = None


@dataclass
class OCRResult:
    provider: str
    extracted_text: str
    confidence_score: Decimal
    page_count: int
    processing_time_ms: int
    raw_response: dict
    line_items: list[OCRLineItem]
    vendor_name: str | None = None
    document_date: str | None = None  # ISO date string
    total_amount: Decimal | None = None
    currency_code: str = "CAD"


class OCRAdapter(ABC):
    @abstractmethod
    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        """Submit file for OCR. Returns structured result."""
        ...
