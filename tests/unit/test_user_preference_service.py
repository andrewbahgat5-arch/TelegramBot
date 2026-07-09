"""Unit tests for services/user_preference_service.py (item #10)."""

from __future__ import annotations

import types

import pytest

from services.user_preference_service import UserPreferences, UserPreferenceService

pytestmark = pytest.mark.asyncio


class FakeStore:
    def __init__(self) -> None:
        self.rows: dict[int, types.SimpleNamespace] = {}

    async def get_by_user_id(self, user_id: int) -> types.SimpleNamespace | None:
        return self.rows.get(user_id)

    async def set_flag(self, user_id: int, field: str, value: bool) -> None:
        row = self.rows.setdefault(
            user_id, types.SimpleNamespace(auto_download_small=False, hide_title=False)
        )
        setattr(row, field, value)


async def test_defaults_when_no_row() -> None:
    prefs = await UserPreferenceService(FakeStore()).get(1)
    assert prefs == UserPreferences(auto_download_small=False, hide_title=False)


async def test_toggle_flips_and_persists() -> None:
    store = FakeStore()
    svc = UserPreferenceService(store)

    assert (await svc.toggle(1, 1)).hide_title is True  # index 1 = hide_title
    both = await svc.toggle(1, 0)  # index 0 = auto_download_small
    assert both.auto_download_small is True and both.hide_title is True
    assert (await svc.toggle(1, 1)).hide_title is False  # flips back off


async def test_unknown_index_is_a_noop() -> None:
    assert await UserPreferenceService(FakeStore()).toggle(1, 99) == UserPreferences()
