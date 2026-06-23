"""Unit tests for RoleFilter (MASTER_PLAN Task 4.7)."""

from __future__ import annotations

from typing import cast

from aiogram.types import TelegramObject

from bot.filters.role_filter import RoleFilter, StaffFilter
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from tests.unit._fakes import FakeUser

_EVENT = cast(TelegramObject, object())


def _snap(role: str) -> UserSnapshot:
    return UserSnapshot.from_row(FakeUser(id=1, telegram_id=1, role=role))


async def test_passes_matching_role() -> None:
    assert await RoleFilter(UserRole.OWNER)(_EVENT, _snap("owner")) is True


async def test_rejects_other_role() -> None:
    assert await RoleFilter(UserRole.OWNER)(_EVENT, _snap("user")) is False


async def test_rejects_when_no_user() -> None:
    assert await RoleFilter(UserRole.OWNER)(_EVENT, None) is False


async def test_staff_filter_accepts_owner_and_moderator() -> None:
    assert await StaffFilter(_EVENT, _snap("owner")) is True
    assert await StaffFilter(_EVENT, _snap("moderator")) is True


async def test_staff_filter_rejects_plain_user() -> None:
    assert await StaffFilter(_EVENT, _snap("user")) is False
