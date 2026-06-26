"""Unit tests for the admin inline panel handlers (Sprint 9.6, F-2/EP-22)."""

from __future__ import annotations

import datetime
from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.handlers.admin_panel import (
    open_panel,
    open_settings,
    panel_navigate,
    panel_write,
)
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.settings_service import InvalidSettingValueError, SettingView
from services.user_service import UserStats


def _signer() -> CallbackSigner:
    return CallbackSigner("a-test-secret")


def _user(role: UserRole = UserRole.OWNER) -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=999,
        role=role,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 26),
        total_downloads=0,
    )


def _session() -> AsyncSession:
    return object()  # type: ignore[return-value]  # factories ignore it


def _call(mock: Any) -> Any:
    """The single await call of an AsyncMock, asserted present (keeps mypy happy)."""
    call = mock.await_args
    assert call is not None
    return call


class _FakeUsers:
    async def get_stats(self) -> UserStats:
        return UserStats(total_users=5, banned_users=1, total_downloads=10)

    async def list_users(self, *, limit: int = 30, offset: int = 0) -> list[UserSnapshot]:
        banned = UserSnapshot(
            id=2,
            telegram_id=555,
            role=UserRole.USER,
            is_banned=True,
            is_premium=False,
            daily_download_count=0,
            daily_download_count_reset_date=datetime.date(2026, 6, 26),
            total_downloads=3,
        )
        return [_user(UserRole.USER), banned]


class _FakeQueue:
    async def depth(self) -> int:
        return 3

    async def active_count(self) -> int:
        return 1


class _FakeSettings:
    async def list_all(self) -> list[SettingView]:
        return [SettingView(key="worker_count", value="3", value_type="int")]

    async def get_view(self, key: str) -> SettingView | None:
        return SettingView(key="maintenance_mode", value="false", value_type="bool")


class _FakeAdmin:
    async def list_jobs(
        self, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[Any]:
        return []

    async def browse_errors(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> list[Any]:
        return []


class _FakeAds:
    async def list_ads(self) -> list[Any]:
        return []


def _callback(signer: CallbackSigner, section: str, action: str) -> Any:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_panel(section, action)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


async def _navigate(
    callback: Any, panel: ParsedPanel, user: UserSnapshot, signer: CallbackSigner
) -> None:
    await panel_navigate(
        callback,
        panel,
        _session(),
        user,
        lambda s: _FakeUsers(),
        lambda s: _FakeSettings(),
        lambda s: _FakeAds(),
        lambda s: _FakeAdmin(),
        _FakeQueue(),
        signer,
    )


# --- entry commands -------------------------------------------------------
async def test_open_panel_sends_main_menu() -> None:
    signer = _signer()
    message: Any = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    await open_panel(message, _user(), signer)
    message.answer.assert_awaited_once()
    call = _call(message.answer)
    assert "Admin Panel" in call.args[0]
    assert call.kwargs["reply_markup"] is not None


async def test_open_settings_lists_values() -> None:
    signer = _signer()
    message: Any = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    await open_settings(message, _session(), _user(), lambda s: _FakeSettings(), signer)
    text = _call(message.answer).args[0]
    assert "Settings" in text and "Workers" in text  # field label rendered


# --- navigation -----------------------------------------------------------
async def test_navigate_main_edits_in_place() -> None:
    signer = _signer()
    callback = _callback(signer, "mn", "op")
    await _navigate(callback, ParsedPanel("mn", "op"), _user(), signer)
    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_navigate_statistics_renders_stats() -> None:
    signer = _signer()
    callback = _callback(signer, "t", "op")
    await _navigate(callback, ParsedPanel("t", "op"), _user(), signer)
    assert "Statistics" in callback.message.edit_text.await_args.args[0]


async def test_navigate_users_list_shows_tappable_rows() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "ls")
    await _navigate(callback, ParsedPanel("u", "ls"), _user(), signer)
    assert "Users" in callback.message.edit_text.await_args.args[0]
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    opened = {
        p.arg
        for row in markup.inline_keyboard
        for b in row
        if (p := signer.unpack_panel(b.callback_data)) is not None and p.action == "inf"
    }
    assert 555 in opened  # the banned fake user is a tappable row


async def test_navigate_moderation_shows_only_banned() -> None:
    signer = _signer()
    callback = _callback(signer, "m", "ls")
    await _navigate(callback, ParsedPanel("m", "ls"), _user(), signer)
    text = callback.message.edit_text.await_args.args[0]
    assert "Banned" in text and "555" in text


async def test_owner_only_section_ignored_for_moderator() -> None:
    signer = _signer()
    callback = _callback(signer, "b", "op")
    await _navigate(callback, ParsedPanel("b", "op"), _user(UserRole.MODERATOR), signer)
    callback.message.edit_text.assert_not_awaited()  # guarded
    callback.answer.assert_awaited_once()


async def test_owner_sees_broadcast_section() -> None:
    signer = _signer()
    callback = _callback(signer, "b", "op")
    await _navigate(callback, ParsedPanel("b", "op"), _user(UserRole.OWNER), signer)
    assert "Broadcast" in callback.message.edit_text.await_args.args[0]


# --- settings stepper write flow (9.6.5) ----------------------------------
class _FakeSettingsRW:
    def __init__(self, value: str = "3") -> None:
        self.value = value
        self.saved: list[tuple[str, str, int | None]] = []
        self.raise_on_save = False

    async def get_view(self, key: str) -> SettingView:
        return SettingView(key=key, value=self.value, value_type="int")

    async def list_all(self) -> list[SettingView]:
        return [SettingView(key="worker_count", value=self.value, value_type="int")]

    async def set_validated(self, key: str, value: str, *, updated_by: int | None = None) -> int:
        if self.raise_on_save:
            raise InvalidSettingValueError("bad value")
        self.saved.append((key, value, updated_by))
        self.value = value
        return int(value)


async def _write(callback: Any, panel: ParsedPanel, settings: _FakeSettingsRW) -> None:
    await panel_write(
        callback,
        panel,
        _session(),
        _user(),
        lambda s: _FakeUsersRW(),
        lambda s: settings,
        _signer(),
    )


async def test_stepper_opens_at_current_value() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "e")
    await _write(callback, ParsedPanel("s", "e", 0), _FakeSettingsRW(value="3"))
    text = callback.message.edit_text.await_args.args[0]
    assert "Workers" in text and "Current value: <b>3</b>" in text


async def test_stepper_increment_rerenders_candidate() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "+")
    await _write(callback, ParsedPanel("s", "+", 0, 4), _FakeSettingsRW())
    assert "Current value: <b>4</b>" in callback.message.edit_text.await_args.args[0]


async def test_stepper_save_persists_via_set_validated() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "sv")
    settings = _FakeSettingsRW()
    await _write(callback, ParsedPanel("s", "sv", 0, 7), settings)
    assert settings.saved == [("worker_count", "7", 1)]  # _user().id == 1
    assert "Saved" in _call(callback.answer).args[0]
    assert "Settings" in callback.message.edit_text.await_args.args[0]  # back to the list


async def test_stepper_save_clamps_out_of_range_value() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "sv")
    settings = _FakeSettingsRW()
    await _write(callback, ParsedPanel("s", "sv", 0, 999), settings)  # field 0 max is 32
    assert settings.saved == [("worker_count", "32", 1)]


async def test_stepper_save_reports_validation_error() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "sv")
    settings = _FakeSettingsRW()
    settings.raise_on_save = True
    await _write(callback, ParsedPanel("s", "sv", 0, 5), settings)
    assert settings.saved == []
    call = _call(callback.answer)
    assert "Couldn't save" in call.args[0] and call.kwargs.get("show_alert") is True


async def test_settings_info_screen_renders() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "inf")
    await _navigate(callback, ParsedPanel("s", "inf", 0), _user(), signer)
    assert "Cache" in callback.message.edit_text.await_args.args[0]


# --- users management write flow (9.6.6) ----------------------------------
class _FakeUsersRW:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.target = UserSnapshot(
            id=555,
            telegram_id=555,
            role=UserRole.USER,
            is_banned=False,
            is_premium=False,
            daily_download_count=0,
            daily_download_count_reset_date=datetime.date(2026, 6, 26),
            total_downloads=0,
        )

    async def find(self, telegram_id: int) -> UserSnapshot | None:
        return self.target if telegram_id == self.target.telegram_id else None

    async def ban(self, telegram_id: int, reason: str | None = None) -> UserSnapshot | None:
        self.calls.append(("ban", telegram_id))
        self.target = replace(self.target, is_banned=True)
        return self.target

    async def unban(self, telegram_id: int) -> UserSnapshot | None:
        self.calls.append(("unban", telegram_id))
        self.target = replace(self.target, is_banned=False)
        return self.target

    async def set_premium(
        self, telegram_id: int, *, is_premium: bool, expires_at: Any = None
    ) -> UserSnapshot | None:
        self.calls.append(("premium", telegram_id, is_premium))
        self.target = replace(self.target, is_premium=is_premium)
        return self.target

    async def set_role(self, telegram_id: int, role: UserRole) -> UserSnapshot | None:
        self.calls.append(("role", telegram_id, role))
        self.target = replace(self.target, role=role)
        return self.target


async def _uwrite(callback: Any, panel: ParsedPanel, users: _FakeUsersRW) -> None:
    await panel_write(
        callback,
        panel,
        _session(),
        _user(),
        lambda s: users,
        lambda s: _FakeSettingsRW(),
        _signer(),
    )


async def test_ban_opens_confirm_without_mutating() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "ban")
    users = _FakeUsersRW()
    await _uwrite(callback, ParsedPanel("u", "ban", 555), users)
    assert users.calls == []  # nothing happened yet
    assert "Confirm" in callback.message.edit_text.await_args.args[0]


async def test_confirmed_ban_mutates_and_rerenders_detail() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "banc")
    users = _FakeUsersRW()
    await _uwrite(callback, ParsedPanel("u", "banc", 555), users)
    assert users.calls == [("ban", 555)]
    assert "Banned" in _call(callback.answer).args[0]
    assert "555" in callback.message.edit_text.await_args.args[0]  # detail re-rendered


async def test_unban_acts_directly() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "ubn")
    users = _FakeUsersRW()
    await _uwrite(callback, ParsedPanel("u", "ubn", 555), users)
    assert users.calls == [("unban", 555)]


async def test_upgrade_premium_acts_directly() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "up")
    users = _FakeUsersRW()
    await _uwrite(callback, ParsedPanel("u", "up", 555), users)
    assert users.calls == [("premium", 555, True)]


async def test_remove_premium_requires_confirm() -> None:
    signer = _signer()
    users = _FakeUsersRW()
    # Opening the action only renders the confirm screen.
    await _uwrite(_callback(signer, "u", "rp"), ParsedPanel("u", "rp", 555), users)
    assert users.calls == []
    # Confirming performs the write.
    await _uwrite(_callback(signer, "u", "rpc"), ParsedPanel("u", "rpc", 555), users)
    assert users.calls == [("premium", 555, False)]


async def test_make_admin_confirm_sets_role() -> None:
    signer = _signer()
    users = _FakeUsersRW()
    await _uwrite(_callback(signer, "u", "mkac"), ParsedPanel("u", "mkac", 555), users)
    assert users.calls == [("role", 555, UserRole.MODERATOR)]


async def test_user_action_without_target_hints_to_list() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "ban")
    users = _FakeUsersRW()
    await _uwrite(callback, ParsedPanel("u", "ban", None), users)
    assert users.calls == []
    assert "List" in _call(callback.answer).args[0]


async def test_user_detail_renders_via_navigation() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "inf")
    users = _FakeUsersRW()
    await panel_navigate(
        callback,
        ParsedPanel("u", "inf", 555),
        _session(),
        _user(),
        lambda s: users,
        lambda s: _FakeSettings(),
        lambda s: _FakeAds(),
        lambda s: _FakeAdmin(),
        _FakeQueue(),
        signer,
    )
    assert "555" in callback.message.edit_text.await_args.args[0]


# --- write stub (ads / broadcast still pending) ---------------------------
async def test_write_stub_acks_for_pending_section() -> None:
    callback: Any = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    await panel_write(
        callback,
        ParsedPanel("a", "cr"),
        _session(),
        _user(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeSettingsRW(),
        _signer(),
    )
    callback.answer.assert_awaited_once()
    assert _call(callback.answer).args  # a toast message was supplied
