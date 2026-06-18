from decimal import Decimal

from pydantic import BaseModel


class PushOpsImportResult(BaseModel):
    rows_parsed: int
    expenses_created: int
    duplicates_skipped: int
    total_amount: Decimal
    currency_code: str
    pay_dates: list[str]
