"""
PushOperations payroll CSV import.

PushOperations does not expose an open API on lower tiers, so labor cost is
ingested via the CSV/Excel export the operator downloads from the PushOps
"Payroll Summary" / "Labor" report. The export column layout differs between
report types and PushOps versions, so the parser fuzzy-matches headers rather
than assuming a fixed schema.

Parsed rows become Payroll-category Expense records (see PnLCalculator), which
flow straight into the P&L Labor Cost line. Parsing is pure and deterministic so
it can be unit-tested without a database; the DB write + dedup lives in the
import service.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

# Header synonyms — matched case-insensitively against the CSV header row.
# Order matters only for documentation; matching scans all candidates.
_EMPLOYEE_HEADERS = ("employee", "employee name", "name", "worker", "staff")
_DATE_HEADERS = (
    "pay date",
    "pay period end",
    "period end",
    "period ending",
    "date",
    "pay period",
)
# Prefer fully-loaded cost columns over plain wages when both exist.
_AMOUNT_HEADERS = (
    "total cost",
    "total labor cost",
    "fully burdened",
    "gross pay",
    "gross",
    "total pay",
    "net pay",
    "amount",
    "total",
)
_LOCATION_HEADERS = ("location", "store", "site", "restaurant", "branch")

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — payroll CSVs are tiny; cap abuse.


class PushOpsParseError(ValueError):
    """Raised when the CSV cannot be parsed into labor line items."""


@dataclass(frozen=True)
class LaborLineItem:
    employee: str | None
    pay_date: date
    amount: Decimal
    location_hint: str | None


def _normalize(header: str) -> str:
    return header.strip().lower().replace("_", " ").replace("-", " ")


def _match_column(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    """Return the index of the first header matching any candidate.

    Matches exact-normalized first (across all candidates), then falls back to
    substring containment, so "Employee Name" matches "employee" and a column
    literally named "Total Cost ($)" still matches "total cost".
    """
    norm = [_normalize(h) for h in headers]
    for cand in candidates:
        for i, h in enumerate(norm):
            if h == cand:
                return i
    for cand in candidates:
        for i, h in enumerate(norm):
            if cand in h:
                return i
    return None


def _parse_amount(raw: str) -> Decimal | None:
    """Parse a money cell. Tolerates $, commas, and parenthesized negatives."""
    s = raw.strip()
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").strip()
    if not s:
        return None
    try:
        val = Decimal(s)
    except InvalidOperation:
        return None
    return -val if negative else val


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m-%d-%Y",
)


def _parse_date(raw: str) -> date | None:
    s = raw.strip()
    if not s:
        return None
    # "period ending 05/31/2026" style — keep the last whitespace token chunk too.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class _SummaryCols:
    pay_date_idx: int
    gross_idx: int
    employer_cpp_idx: int | None
    employer_ei_idx: int | None
    wcb_idx: int | None
    first_col_idx: int  # to detect the trailing "Total" summary row


def _group_owners(grouping_row: list[str] | None, width: int) -> list[str]:
    """Forward-fill a merged grouping row into a per-column owner label.

    PushOps merges "Employee"/"Employer"/"Government Remittance" across several
    columns, leaving the continuation cells blank. Forward-fill so each column
    knows which group it belongs to (needed to tell employee CPP/EI from the
    identically-named employer CPP/EI).
    """
    owners = [""] * width
    if not grouping_row:
        return owners
    current = ""
    for i in range(width):
        cell = grouping_row[i].strip().lower() if i < len(grouping_row) else ""
        if cell:
            current = cell
        owners[i] = current
    return owners


def _summary_columns(
    headers: list[str], grouping_row: list[str] | None
) -> _SummaryCols | None:
    """Detect the 'Payroll Summary by Period' layout and map its columns.

    Returns None if this is not the summary layout (caller falls back to the
    simple per-employee path).
    """
    norm = [_normalize(h) for h in headers]
    gross_idx = next((i for i, h in enumerate(norm) if h == "total gross"), None)
    pay_date_idx = next((i for i, h in enumerate(norm) if h == "pay date"), None)
    if gross_idx is None or pay_date_idx is None:
        return None

    owners = _group_owners(grouping_row, len(headers))

    def _find(header_name: str, owner: str | None = None) -> int | None:
        for i, h in enumerate(norm):
            if h == header_name and (owner is None or owners[i] == owner):
                return i
        return None

    employer_cpp_idx = _find("total cpp", "employer")
    employer_ei_idx = _find("total ei", "employer")
    wcb_idx = _find("total wcb")  # WCB is employer-only; no grouping needed

    return _SummaryCols(
        pay_date_idx=pay_date_idx,
        gross_idx=gross_idx,
        employer_cpp_idx=employer_cpp_idx,
        employer_ei_idx=employer_ei_idx,
        wcb_idx=wcb_idx,
        first_col_idx=0,
    )


def _cell_amount(row: list[str], idx: int | None) -> Decimal:
    if idx is None or idx >= len(row):
        return Decimal("0")
    return _parse_amount(row[idx]) or Decimal("0")


def _parse_summary(
    headers: list[str],
    data_rows: list[list[str]],
    cols: _SummaryCols,
    fallback_pay_date: date | None,
) -> list[LaborLineItem]:
    items: list[LaborLineItem] = []
    for row in data_rows:
        # Trailing "Total" row has no pay date and a "Total" label in col 0.
        first = row[cols.first_col_idx].strip().lower() if cols.first_col_idx < len(row) else ""
        if first in ("total", "totals", "grand total"):
            continue

        pay_date = None
        if cols.pay_date_idx < len(row):
            pay_date = _parse_date(row[cols.pay_date_idx])
        if pay_date is None:
            pay_date = fallback_pay_date
        if pay_date is None:
            continue

        gross = _cell_amount(row, cols.gross_idx)
        # Fully-burdened employer labor cost = gross wages + employer-side
        # statutory costs. This is the real cost to the business for the P&L.
        burden = (
            _cell_amount(row, cols.employer_cpp_idx)
            + _cell_amount(row, cols.employer_ei_idx)
            + _cell_amount(row, cols.wcb_idx)
        )
        amount = gross + burden
        if amount == 0:
            continue
        items.append(
            LaborLineItem(
                employee=None,
                pay_date=pay_date,
                amount=amount,
                location_hint=None,
            )
        )
    if not items:
        raise PushOpsParseError("No valid payroll rows found in CSV")
    return items


def parse_pushops_csv(
    file_bytes: bytes,
    fallback_pay_date: date | None = None,
) -> list[LaborLineItem]:
    """Parse a PushOperations payroll CSV export into labor line items.

    `fallback_pay_date` is used for rows missing a parseable date (or when the
    export has no date column at all — e.g. a single-period summary). If a row
    has no date and no fallback is given, that row is skipped.

    Raises PushOpsParseError if the file is empty, too large, not decodable, or
    has no recognizable amount column.
    """
    if not file_bytes:
        raise PushOpsParseError("Empty file")
    if len(file_bytes) > _MAX_BYTES:
        raise PushOpsParseError("File too large (max 5 MB)")

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("latin-1")
        except UnicodeDecodeError as exc:  # pragma: no cover - latin-1 rarely fails
            raise PushOpsParseError("File is not valid text/CSV") from exc

    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if len(rows) < 2:
        raise PushOpsParseError("CSV has no data rows")

    # PushOps exports can carry a grouping row ("Employee / Employer / Government
    # Remittance") above the real header row, so the header is not always row 0.
    # Locate the header row as the first row that contains an amount column.
    header_idx = None
    for i, row in enumerate(rows):
        if _match_column(row, _AMOUNT_HEADERS) is not None:
            header_idx = i
            break
    if header_idx is None:
        raise PushOpsParseError(
            "Could not find a pay/amount column. Expected one of: "
            + ", ".join(_AMOUNT_HEADERS)
        )

    headers = rows[header_idx]
    data_rows = rows[header_idx + 1 :]
    grouping_row = rows[header_idx - 1] if header_idx > 0 else None

    # "Payroll Summary by Period" format: per-period rows with a Total Gross plus
    # separate employee/employer deductions. The figure that matters for the P&L
    # is the fully-burdened employer cost = gross + employer CPP + employer EI + WCB.
    summary = _summary_columns(headers, grouping_row)
    if summary is not None:
        return _parse_summary(headers, data_rows, summary, fallback_pay_date)

    amount_idx = _match_column(headers, _AMOUNT_HEADERS)
    assert amount_idx is not None  # guaranteed by header_idx search
    employee_idx = _match_column(headers, _EMPLOYEE_HEADERS)
    date_idx = _match_column(headers, _DATE_HEADERS)
    location_idx = _match_column(headers, _LOCATION_HEADERS)

    items: list[LaborLineItem] = []
    for row in data_rows:
        if amount_idx >= len(row):
            continue
        amount = _parse_amount(row[amount_idx])
        if amount is None or amount == 0:
            continue
        # Skip a trailing "Total"/"Grand Total" summary row to avoid double count.
        if employee_idx is not None and employee_idx < len(row):
            emp_cell = row[employee_idx].strip()
            if emp_cell.lower() in ("total", "grand total", "totals"):
                continue
            employee = emp_cell or None
        else:
            employee = None

        pay_date: date | None = None
        if date_idx is not None and date_idx < len(row):
            pay_date = _parse_date(row[date_idx])
        if pay_date is None:
            pay_date = fallback_pay_date
        if pay_date is None:
            continue

        location_hint = None
        if location_idx is not None and location_idx < len(row):
            location_hint = row[location_idx].strip() or None

        items.append(
            LaborLineItem(
                employee=employee,
                pay_date=pay_date,
                amount=amount,
                location_hint=location_hint,
            )
        )

    if not items:
        raise PushOpsParseError("No valid payroll rows found in CSV")
    return items


def to_datetime(d: date) -> datetime:
    """Expense.expense_date is timezone-aware; assign UTC midnight."""
    return datetime(d.year, d.month, d.day, tzinfo=UTC)
