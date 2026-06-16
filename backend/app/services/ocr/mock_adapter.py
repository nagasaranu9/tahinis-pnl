import asyncio
import hashlib
from decimal import Decimal

from app.services.ocr.base import OCRAdapter, OCRLineItem, OCRResult


class MockOCRAdapter(OCRAdapter):
    """
    Returns deterministic fixture data based on file content hash.
    Used for development and testing. Swap for GoogleDocumentAIAdapter in production.
    """

    async def process(self, file_bytes: bytes, mime_type: str) -> OCRResult:
        await asyncio.sleep(0.1)  # simulate latency

        # Deterministic variation based on file hash
        file_hash = hashlib.sha256(file_bytes).hexdigest()
        seed = int(file_hash[:8], 16) % 4

        fixtures = [
            self._sysco_invoice(),
            self._utility_bill(),
            self._packaging_receipt(),
            self._cleaning_supplies(),
        ]
        return fixtures[seed]

    def _sysco_invoice(self) -> OCRResult:
        return OCRResult(
            provider="mock",
            extracted_text="""SYSCO CANADA
Invoice #: INV-2026-04821
Date: 2026-06-10
Bill To: Tahinis Restaurant

Item                          Qty    Unit Price    Amount
-------------------------------------------------------
Chicken Breast (10kg)          5      $45.00      $225.00
Tomatoes Roma (case)           3      $28.00       $84.00
Olive Oil Extra Virgin (4L)    2      $32.00       $64.00
Pita Bread (100pk)             4      $18.00       $72.00
                                              ----------
                              Subtotal:       $445.00
                              HST (13%):       $57.85
                              TOTAL:          $502.85
""",
            confidence_score=Decimal("0.9750"),
            page_count=1,
            processing_time_ms=312,
            raw_response={"mock": True, "fixture": "sysco_invoice"},
            line_items=[
                OCRLineItem("Chicken Breast (10kg)", Decimal("225.00"), Decimal("0.98"), Decimal("5"), Decimal("45.00")),
                OCRLineItem("Tomatoes Roma (case)", Decimal("84.00"), Decimal("0.97"), Decimal("3"), Decimal("28.00")),
                OCRLineItem("Olive Oil Extra Virgin (4L)", Decimal("64.00"), Decimal("0.96"), Decimal("2"), Decimal("32.00")),
                OCRLineItem("Pita Bread (100pk)", Decimal("72.00"), Decimal("0.99"), Decimal("4"), Decimal("18.00")),
            ],
            vendor_name="Sysco Canada",
            document_date="2026-06-10",
            total_amount=Decimal("502.85"),
            currency_code="CAD",
        )

    def _utility_bill(self) -> OCRResult:
        return OCRResult(
            provider="mock",
            extracted_text="""TORONTO HYDRO
Account: 4821-992-001
Billing Period: May 1 - May 31, 2026
Service Address: 123 King St W

Current Charges:
  Energy Charges:        $892.44
  Delivery Charges:      $210.00
  Regulatory Charges:     $45.00
  HST (13%):             $150.34

TOTAL AMOUNT DUE:       $1,297.78
Due Date: June 25, 2026
""",
            confidence_score=Decimal("0.9820"),
            page_count=1,
            processing_time_ms=245,
            raw_response={"mock": True, "fixture": "utility_bill"},
            line_items=[
                OCRLineItem("Energy Charges", Decimal("892.44"), Decimal("0.99")),
                OCRLineItem("Delivery Charges", Decimal("210.00"), Decimal("0.98")),
                OCRLineItem("Regulatory Charges", Decimal("45.00"), Decimal("0.97")),
            ],
            vendor_name="Toronto Hydro",
            document_date="2026-05-31",
            total_amount=Decimal("1297.78"),
            currency_code="CAD",
        )

    def _packaging_receipt(self) -> OCRResult:
        return OCRResult(
            provider="mock",
            extracted_text="""ULINE SHIPPING SUPPLIES
Order #: 12984771
Date: 2026-06-08

Kraft Paper Bags 8x4x10 (250pk)   $89.00
Compostable Containers 32oz (500)  $145.00
Paper Straws Wrapped (1000pk)       $42.00
                            --------
                  Subtotal:  $276.00
                  HST:        $35.88
                  TOTAL:     $311.88
""",
            confidence_score=Decimal("0.9610"),
            page_count=1,
            processing_time_ms=198,
            raw_response={"mock": True, "fixture": "packaging_receipt"},
            line_items=[
                OCRLineItem("Kraft Paper Bags 8x4x10 (250pk)", Decimal("89.00"), Decimal("0.96")),
                OCRLineItem("Compostable Containers 32oz (500)", Decimal("145.00"), Decimal("0.97")),
                OCRLineItem("Paper Straws Wrapped (1000pk)", Decimal("42.00"), Decimal("0.95")),
            ],
            vendor_name="Uline",
            document_date="2026-06-08",
            total_amount=Decimal("311.88"),
            currency_code="CAD",
        )

    def _cleaning_supplies(self) -> OCRResult:
        return OCRResult(
            provider="mock",
            extracted_text="""CINTAS CANADA
Service Date: 2026-06-09
Route #: RT-4421

Kitchen Mat Service (weekly)    $65.00
Mop Head Replacement x4         $48.00
Sanitizer Dispenser Refill x6   $72.00
                         --------
             Subtotal:   $185.00
             HST:         $24.05
             TOTAL:      $209.05
""",
            confidence_score=Decimal("0.9540"),
            page_count=1,
            processing_time_ms=221,
            raw_response={"mock": True, "fixture": "cleaning_supplies"},
            line_items=[
                OCRLineItem("Kitchen Mat Service (weekly)", Decimal("65.00"), Decimal("0.96")),
                OCRLineItem("Mop Head Replacement x4", Decimal("48.00"), Decimal("0.95")),
                OCRLineItem("Sanitizer Dispenser Refill x6", Decimal("72.00"), Decimal("0.96")),
            ],
            vendor_name="Cintas Canada",
            document_date="2026-06-09",
            total_amount=Decimal("209.05"),
            currency_code="CAD",
        )
