"""Unit tests for the UserSnapshot entity (MASTER_PLAN Task 4.1)."""

from __future__ import annotations

import datetime

from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from tests.unit._fakes import FakeUser


def _row() -> FakeUser:
    return FakeUser(
        id=7,
        telegram_id=123456789,
        role="owner",
        is_premium=True,
        premium_expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
        daily_download_count=3,
        total_downloads=42,
        username="neo",
        first_name="Thomas",
        language="en",
        last_activity_at=datetime.datetime(2026, 6, 23, 12, 0, tzinfo=datetime.UTC),
        created_at=datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC),
    )


def test_from_row_maps_role_to_enum() -> None:
    snap = UserSnapshot.from_row(_row())
    assert snap.role is UserRole.OWNER
    assert snap.id == 7
    assert snap.telegram_id == 123456789
    assert snap.is_premium is True
    assert snap.created_at == datetime.datetime(2026, 1, 1, 9, 0, tzinfo=datetime.UTC)


def test_cache_round_trip_is_lossless() -> None:
    snap = UserSnapshot.from_row(_row())
    restored = UserSnapshot.from_cache_dict(snap.to_cache_dict())
    assert restored == snap


def test_cache_dict_is_json_primitive() -> None:
    data = UserSnapshot.from_row(_row()).to_cache_dict()
    # Timestamps/dates are serialised to strings, role to its value.
    assert data["role"] == "owner"
    assert isinstance(data["daily_download_count_reset_date"], str)
    assert isinstance(data["premium_expires_at"], str)


def test_round_trip_with_null_optionals() -> None:
    row = FakeUser(id=1, telegram_id=99, daily_download_count_reset_date=datetime.date(2026, 6, 23))
    snap = UserSnapshot.from_row(row)
    restored = UserSnapshot.from_cache_dict(snap.to_cache_dict())
    assert restored.premium_expires_at is None
    assert restored.last_activity_at is None
    assert restored.username is None
    assert restored == snap
