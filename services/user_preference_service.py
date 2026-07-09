"""UserPreferenceService (item #10) — per-user Settings toggles.

Owns the small set of self-service preferences a user flips from the Settings screen
(auto-download small files; hide parts of the delivered caption). Read at delivery time
to shape behavior. The toggle set is a data-driven registry so new toggles (the deferred
meta/description ones) are one entry, not a handler change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """A user's effective preferences (defaults = current behavior when no row exists)."""

    auto_download_small: bool = False
    hide_title: bool = False


@dataclass(frozen=True, slots=True)
class SettingToggle:
    """One Settings-screen toggle: its stable ``index`` (callback arg), the model field
    it flips, and the i18n key for its button label."""

    index: int
    field: str
    label_key: str


# Stable indices — the compact callback arg. Append-only (meta/description are phase 2).
SETTING_TOGGLES: tuple[SettingToggle, ...] = (
    SettingToggle(0, "auto_download_small", "settings.toggle.auto_download"),
    SettingToggle(1, "hide_title", "settings.toggle.hide_title"),
)


def toggle_at(index: int | None) -> SettingToggle | None:
    if index is not None and 0 <= index < len(SETTING_TOGGLES):
        return SETTING_TOGGLES[index]
    return None


class UserPreferenceStore(Protocol):
    async def get_by_user_id(self, user_id: int) -> Any | None: ...
    async def set_flag(self, user_id: int, field: str, value: bool) -> None: ...


class UserPreferenceService:
    def __init__(self, store: UserPreferenceStore) -> None:
        self._store = store

    async def get(self, user_id: int) -> UserPreferences:
        row = await self._store.get_by_user_id(user_id)
        if row is None:
            return UserPreferences()
        return UserPreferences(
            auto_download_small=bool(getattr(row, "auto_download_small", False)),
            hide_title=bool(getattr(row, "hide_title", False)),
        )

    async def toggle(self, user_id: int, index: int) -> UserPreferences:
        """Flip the toggle at ``index`` and return the updated preferences (no-op if unknown)."""
        toggle = toggle_at(index)
        if toggle is None:
            return await self.get(user_id)
        current = await self.get(user_id)
        await self._store.set_flag(user_id, toggle.field, not getattr(current, toggle.field))
        return await self.get(user_id)
