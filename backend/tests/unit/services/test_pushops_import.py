from datetime import date
from decimal import Decimal

import pytest

from app.services.labor.pushops_import import (
    LaborLineItem,
    PushOpsParseError,
    parse_pushops_csv,
    to_datetime,
)


def _csv(text: str) -> bytes:
    return text.encode("utf-8")


def test_parses_standard_export():
    data = _csv(
        "Employee,Pay Date,Gross Pay,Location\n"
        "Alice Smith,2026-05-31,1500.00,Church & Bloor\n"
        "Bob Jones,2026-05-31,1200.50,Church & Bloor\n"
    )
    items = parse_pushops_csv(data)
    assert len(items) == 2
    assert items[0] == LaborLineItem(
        employee="Alice Smith",
        pay_date=date(2026, 5, 31),
        amount=Decimal("1500.00"),
        location_hint="Church & Bloor",
    )


def test_fuzzy_headers_and_money_formatting():
    data = _csv(
        "Employee Name,Period Ending,Total Cost ($)\n"
        'Alice,"05/31/2026","$1,500.00"\n'
    )
    items = parse_pushops_csv(data)
    assert items[0].amount == Decimal("1500.00")
    assert items[0].pay_date == date(2026, 5, 31)


def test_prefers_total_cost_over_gross():
    data = _csv(
        "Employee,Pay Date,Gross Pay,Total Cost\n"
        "Alice,2026-05-31,1000.00,1325.00\n"
    )
    items = parse_pushops_csv(data)
    assert items[0].amount == Decimal("1325.00")


def test_skips_total_row():
    data = _csv(
        "Employee,Pay Date,Gross Pay\n"
        "Alice,2026-05-31,1000.00\n"
        "Total,,1000.00\n"
    )
    items = parse_pushops_csv(data)
    assert len(items) == 1


def test_parenthesized_negative():
    data = _csv("Employee,Pay Date,Amount\nAlice,2026-05-31,(50.00)\n")
    items = parse_pushops_csv(data)
    assert items[0].amount == Decimal("-50.00")


def test_fallback_pay_date_when_no_date_column():
    data = _csv("Employee,Gross Pay\nAlice,1000.00\n")
    items = parse_pushops_csv(data, fallback_pay_date=date(2026, 5, 31))
    assert items[0].pay_date == date(2026, 5, 31)


def test_row_without_date_and_no_fallback_skipped():
    data = _csv("Employee,Gross Pay\nAlice,1000.00\n")
    with pytest.raises(PushOpsParseError):
        parse_pushops_csv(data)


def test_missing_amount_column_raises():
    data = _csv("Employee,Pay Date,Hours\nAlice,2026-05-31,40\n")
    with pytest.raises(PushOpsParseError, match="amount column"):
        parse_pushops_csv(data)


def test_empty_file_raises():
    with pytest.raises(PushOpsParseError):
        parse_pushops_csv(b"")


def test_zero_amounts_skipped():
    data = _csv(
        "Employee,Pay Date,Gross Pay\n"
        "Alice,2026-05-31,0.00\n"
        "Bob,2026-05-31,500.00\n"
    )
    items = parse_pushops_csv(data)
    assert len(items) == 1
    assert items[0].employee == "Bob"


def test_utf8_bom_handled():
    data = "﻿Employee,Pay Date,Gross Pay\nAlice,2026-05-31,100.00\n".encode("utf-8")
    items = parse_pushops_csv(data)
    assert items[0].amount == Decimal("100.00")


def test_to_datetime_is_utc_midnight():
    dt = to_datetime(date(2026, 5, 31))
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 5, 31, 0)
    assert dt.tzinfo is not None
