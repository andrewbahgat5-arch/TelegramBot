"""Unit tests for core.timeparse (MASTER_PLAN Task 9.5.10)."""

from __future__ import annotations

import datetime

import pytest

from core.timeparse import parse_iso_datetime


def test_parses_trailing_z_as_utc() -> None:
    parsed = parse_iso_datetime("2026-07-01T12:00:00Z")
    assert parsed == datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)
    assert parsed.tzinfo == datetime.UTC


def test_naive_input_assumed_utc() -> None:
    parsed = parse_iso_datetime("2026-07-01T12:00:00")
    assert parsed == datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)


def test_explicit_offset_converted_to_utc() -> None:
    parsed = parse_iso_datetime("2026-07-01T15:00:00+03:00")
    assert parsed == datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)


def test_date_only_is_midnight_utc() -> None:
    assert parse_iso_datetime("2026-07-01") == datetime.datetime(2026, 7, 1, tzinfo=datetime.UTC)


@pytest.mark.parametrize("bad", ["", "   ", "not-a-date", "2026-13-01", "tomorrow"])
def test_malformed_raises_value_error(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_iso_datetime(bad)
