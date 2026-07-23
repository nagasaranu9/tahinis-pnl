"""Parse a bank / credit-card statement CSV into money-OUT transactions.

CSV exports carry full dates and exact amounts, so they're a cleaner truth than
OCR-ing a PDF (no scan errors, no yearless-date guessing, no LLM cost). This
module auto-detects the column layout of the common Canadian bank/CC exports
(BMO, TD, RBC, Scotia, Amex) and emits one dict per outflow row:

    {"description": str, "amount": Decimal(> 0), "date": "YYYY-MM-DD"}

Only debits/purchases (money out) are returned — deposits/credits are revenue,
not expenses. The worker path applies the same non-expense filters + dedup +
categorization it uses for OCR'd statements, so this stays deliberately dumb.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import structlog

logger = structlog.get_logger(__name__)

# Header keywords → semantic column role.
_DATE_KEYS = ("date", "posted", "posting", "transaction date", "trans date")
# NB: no bare "transaction" — it collides with "Transaction Type"/"Transaction Date".
_DESC_KEYS = ("description", "details", "payee", "memo", "narrative", "name")
_DEBIT_KEYS = ("debit", "withdrawal", "withdrawals", "money out", "paid out", "charge")
_CREDIT_KEYS = ("credit", "deposit", "deposits", "money in", "paid in")
_AMOUNT_KEYS = ("amount", "transaction amount", "cad$", "value")
_BALANCE_KEYS = ("balance",)

_CARD_HINTS = ("mastercard", "visa", "amex", "credit card", "ascend", "world elite")


def _clean_money(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):  # (123.45) accounting negative
        neg = True
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.endswith("-"):  # trailing-minus format
        neg = True
        s = s[:-1]
    if s in ("", "-", "."):
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if neg else val


_DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y", "%d/%m/%y",
    "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y%m%d", "%m-%d-%Y", "%d-%m-%Y",
)


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    s = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _decode(file_bytes: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="replace")


def _match_col(header: list[str], keys: tuple[str, ...]) -> int | None:
    """Index of the first header cell containing any key (longest key wins on ties)."""
    best_idx: int | None = None
    best_len = 0
    for i, cell in enumerate(header):
        c = (cell or "").strip().lower()
        for k in keys:
            if k in c and len(k) > best_len:
                best_idx = i
                best_len = len(k)
    return best_idx


def _looks_like_header(row: list[str]) -> bool:
    joined = " ".join(row).lower()
    return any(k in joined for k in ("date", "amount", "description", "debit", "credit", "balance"))


def _normalize_desc(desc: str) -> str:
    """Clean a BMO statement description and interpret its [XX] type-code.

    BMO CSV descriptions carry a two-letter transaction-type code in brackets
    ([DS] pre-auth, [SO] standing order, [IN] interest, [MB]/[CW] withdrawal,
    [DN] bill payment, [IB]/[SC] …) plus column padding. The bare code breaks the
    downstream keyword categorizer, dedup and AMEX-rent detection, so we strip it
    and, for the codes that carry accounting meaning, rewrite the text into the
    phrasing the existing pipeline already understands.
    """
    desc = re.sub(r"\s+", " ", desc).strip()
    m = re.match(r"^\[([A-Z]{2})\]\s*(.*)$", desc)
    code, rest = (m.group(1), m.group(2).strip()) if m else ("", desc)
    low = rest.lower()

    # AMEX card autopay = rent (tenant-confirmed). BMO labels it "[CW]AMEX CARDS".
    if "amex" in low:
        return "ONLINE BILL PAYMENT, AMEX CARDS"
    # BMO loan account 3699#6999-671: standing orders = principal, [IN] = interest.
    if code == "IN":
        return f"INTEREST PAID {rest}"
    if code == "SO":
        return f"LOAN PAYMENT {rest}"
    # [DN]BMO PAYMENT = automatic Mastercard bill payment (clears the card).
    if "bmo payment" in low:
        return "CREDIT CARD PAYMENT, BMO"
    # ABM / branch cash withdrawals (BR.####) — tenant books these to staffing.
    if re.search(r"\bbr\.?\d{3,4}\b", low):
        return f"STAFFING CASH WITHDRAWAL {rest}"
    return rest or desc


def parse_statement_csv(file_bytes: bytes, filename: str = "") -> dict:
    """Parse a statement CSV. Returns document_date, currency, and outflow txns.

    Raises ValueError when the layout can't be understood (no date or no amount
    column identifiable) so the caller can surface a clear error.
    """
    text = _decode(file_bytes)
    # Sniff delimiter from a sample; default to comma.
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if any(c.strip() for c in r)]
    if not rows:
        raise ValueError("CSV is empty")

    # Find the header row (BMO/others prepend account-info lines before the table).
    header_idx = next((i for i, r in enumerate(rows[:15]) if _looks_like_header(r)), None)
    if header_idx is None:
        raise ValueError("Could not find a header row (need Date / Amount / Description columns)")
    header = [c.strip() for c in rows[header_idx]]
    body = rows[header_idx + 1 :]

    date_i = _match_col(header, _DATE_KEYS)
    debit_i = _match_col(header, _DEBIT_KEYS)
    credit_i = _match_col(header, _CREDIT_KEYS)
    amount_i = _match_col(header, _AMOUNT_KEYS)
    balance_i = _match_col(header, _BALANCE_KEYS)
    desc_i = _match_col(header, _DESC_KEYS)

    # Amount column must not collide with the balance column.
    if amount_i is not None and amount_i == balance_i:
        amount_i = None

    if date_i is None:
        raise ValueError("No date column found in CSV")
    if debit_i is None and amount_i is None:
        raise ValueError("No amount/debit column found in CSV")

    is_card = any(h in filename.lower() for h in _CARD_HINTS) or any(
        h in " ".join(header).lower() for h in _CARD_HINTS
    )

    txns: list[dict] = []
    latest: date | None = None
    dropped = 0
    for r in body:
        if len(r) <= date_i:
            continue
        d = _parse_date(r[date_i])
        if d is None:
            dropped += 1
            continue
        if latest is None or d > latest:
            latest = d

        # Determine the money-OUT amount (positive) for this row.
        out: Decimal | None = None
        if debit_i is not None and len(r) > debit_i:
            dv = _clean_money(r[debit_i])
            if dv is not None and dv != 0:
                out = abs(dv)  # dedicated debit column is always an outflow
        if out is None and debit_i is None and amount_i is not None and len(r) > amount_i:
            av = _clean_money(r[amount_i])
            if av is not None and av != 0:
                # Single signed amount column. Bank: negative = money out.
                # Credit card: a positive amount is a purchase (money out); a
                # negative is a payment/refund (skip — not an expense).
                if is_card:
                    out = av if av > 0 else None
                else:
                    out = -av if av < 0 else None
        if out is None or out <= 0:
            continue

        raw_desc = (r[desc_i].strip() if desc_i is not None and len(r) > desc_i else "").strip()
        desc = _normalize_desc(raw_desc) if raw_desc else "CSV transaction"
        txns.append({"description": desc, "amount": out, "date": d.isoformat()})

    logger.info(
        "csv_statement_parsed",
        rows=len(body),
        outflows=len(txns),
        dropped_no_date=dropped,
        is_card=is_card,
        cols={"date": date_i, "debit": debit_i, "credit": credit_i, "amount": amount_i, "desc": desc_i},
    )
    if not txns:
        raise ValueError("No outflow (debit/purchase) rows found in CSV")

    return {
        "document_date": (latest or date.today()).isoformat(),
        "currency_code": "CAD",
        "transactions": txns,
    }
