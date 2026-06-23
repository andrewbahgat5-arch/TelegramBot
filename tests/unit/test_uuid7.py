"""Unit tests for core/uuid7.py (MASTER_PLAN D-013)."""

from __future__ import annotations

import uuid
from itertools import pairwise

import pytest

from core.uuid7 import uuid7, uuid7_str


def test_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_monotonic_non_decreasing_across_1000_calls() -> None:
    # Validation checklist: monotonically non-decreasing across 1000 rapid calls.
    ints = [uuid7().int for _ in range(1000)]
    assert ints == sorted(ints)
    # In fact strictly increasing within a process (counter + timestamp).
    assert all(b > a for a, b in pairwise(ints))


def test_uniqueness() -> None:
    values = {uuid7() for _ in range(10_000)}
    assert len(values) == 10_000


def test_uuid7_str_is_valid_uuid() -> None:
    text = uuid7_str()
    parsed = uuid.UUID(text)
    assert parsed.version == 7
    assert str(parsed) == text


def test_counter_overflow_borrows_next_millisecond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Freeze the clock so every call lands in the same millisecond, forcing the
    # 12-bit counter to overflow and borrow from the next millisecond.
    monkeypatch.setattr("core.uuid7.time.time_ns", lambda: 1_700_000_000_000_000_000)
    ints = [uuid7().int for _ in range(5000)]
    assert all(b > a for a, b in pairwise(ints)), "must stay strictly increasing"
    assert len(set(ints)) == len(ints)
