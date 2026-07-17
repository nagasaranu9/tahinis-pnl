"""Unit tests for the PushOperations API client.

Covers the two things most likely to corrupt the Labor line: date chunking
(a gap silently drops a day of labor) and money conversion (float money is
banned, and the API sends unrounded floats).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.services.labor.push_client import (
    MAX_LABOUR_RANGE_DAYS,
    _parse_push_datetime,
    _to_hours,
    _to_money,
    iter_date_chunks,
)


class TestIterDateChunks:
    def test_single_day(self):
        assert list(iter_date_chunks(date(2026, 1, 1), date(2026, 1, 1))) == [
            (date(2026, 1, 1), date(2026, 1, 1))
        ]

    def test_never_exceeds_api_range_limit(self):
        chunks = list(iter_date_chunks(date(2026, 1, 1), date(2026, 7, 17)))
        assert chunks, "expected at least one chunk"
        for start, end in chunks:
            assert (end - start).days <= MAX_LABOUR_RANGE_DAYS

    def test_chunks_are_contiguous_and_cover_range_exactly(self):
        start, end = date(2026, 1, 1), date(2026, 7, 17)
        chunks = list(iter_date_chunks(start, end))
        assert chunks[0][0] == start
        assert chunks[-1][1] == end
        # No gap (a gap = a silently missing day of labor cost) and no overlap
        # (an overlap would be harmless thanks to upsert, but signals a bug).
        for (_, prev_end), (next_start, _) in zip(chunks, chunks[1:]):
            assert next_start == prev_end + timedelta(days=1)

    def test_every_date_covered_exactly_once(self):
        start, end = date(2026, 3, 1), date(2026, 3, 31)
        seen: list[date] = []
        for cs, ce in iter_date_chunks(start, end):
            d = cs
            while d <= ce:
                seen.append(d)
                d += timedelta(days=1)
        expected = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        assert seen == expected

    def test_backwards_range_rejected(self):
        with pytest.raises(ValueError, match="is after end"):
            list(iter_date_chunks(date(2026, 2, 1), date(2026, 1, 1)))


class TestMoneyConversion:
    def test_unrounded_api_float_quantized_to_cents(self):
        # Real value observed from GET /labour/employee.
        assert _to_money(153.84615384615) == Decimal("153.85")

    def test_returns_decimal_not_float(self):
        assert isinstance(_to_money(10.5), Decimal)

    def test_none_is_zero_not_none(self):
        assert _to_money(None) == Decimal("0.00")
        assert _to_hours(None) == Decimal("0.00")

    def test_half_up_rounding(self):
        assert _to_money(1.005) == Decimal("1.01")

    def test_string_input_from_json(self):
        assert _to_money("74.8") == Decimal("74.80")

    def test_no_binary_float_artifact(self):
        # Decimal(float) would give 0.070000000000000006...; str() avoids it.
        assert _to_money(0.07) == Decimal("0.07")

    def test_hours_quantized(self):
        assert _to_hours(4.25) == Decimal("4.25")
        assert _to_hours(5) == Decimal("5.00")


class TestParsePushDatetime:
    def test_normal_timestamp(self):
        assert _parse_push_datetime("2026-07-17 09:27:16") == datetime(2026, 7, 17, 9, 27, 16)

    def test_zero_datetime_sentinel_is_none(self):
        # Real value observed from GET /clocks for an employee still clocked
        # in — the API sends this literal string, not null.
        assert _parse_push_datetime("0000-00-00 00:00:00") is None

    def test_none_input_is_none(self):
        assert _parse_push_datetime(None) is None

    def test_empty_string_is_none(self):
        assert _parse_push_datetime("") is None

    def test_negative_year_underflow_sentinel_is_none(self):
        # Second sentinel form observed live for an open clock-out — a
        # timezone-shifted underflow of the zero-date, not a real timestamp.
        assert _parse_push_datetime("-0001-11-29 19:00:00") is None

    def test_unrecognized_garbage_is_none_not_a_crash(self):
        assert _parse_push_datetime("not-a-date") is None
