"""Unit tests for the admin inline panel handlers (Sprint 9.6, F-2/EP-22)."""

from __future__ import annotations

import datetime
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.handlers.admin_panel import (
    on_setting_value,
    on_user_lookup,
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


def _state(data: dict[str, Any] | None = None) -> Any:
    """A fake FSMContext: records set_state/update_data/clear; returns ``data`` on get_data."""
    fsm = AsyncMock()
    fsm.get_data = AsyncMock(return_value=data or {})
    return fsm


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

    async def get(self, key: str) -> Any:
        return 10  # a daily-limit value for the User Info view


class _FakeAdmin:
    async def list_jobs(
        self, *, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> list[Any]:
        return []

    async def browse_errors(
        self, *, limit: int = 50, offset: int = 0, error_type: str | None = None
    ) -> list[Any]:
        return []

    async def count_user_downloads(self, user_id: int) -> int:
        return 7

    async def count_user_active_jobs(self, user_id: int) -> int:
        return 1


class _FakeAd:
    def __init__(self, ad_id: int = 1, *, is_active: bool = True) -> None:
        self.id = ad_id
        self.title = "Promo"
        self.type = "text"
        self.is_active = is_active
        self.impressions = 100
        self.clicks = 10
        self.priority = 1000
        self.show_every_n_downloads = 1
        self.target_role = None


class _FakeAds:
    def __init__(self) -> None:
        self.ad = _FakeAd()
        self.calls: list[tuple[Any, ...]] = []

    async def list_ads(self) -> list[Any]:
        return [self.ad]

    async def get(self, ad_id: int) -> Any:
        return self.ad if ad_id == self.ad.id else None

    async def set_active(self, ad_id: int, active: bool) -> Any:
        self.calls.append(("set_active", ad_id, active))
        if ad_id != self.ad.id:
            return None
        self.ad.is_active = active
        return self.ad

    async def delete(self, ad_id: int) -> bool:
        self.calls.append(("delete", ad_id))
        return ad_id == self.ad.id

    async def overall_stats(self) -> Any:
        return SimpleNamespace(total_ads=1, active_ads=1, impressions=100, clicks=10)


class _FakeBroadcasts:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    async def create_from_ad(
        self,
        *,
        created_by_user_id: int,
        advertisement_id: int,
        target_language: str | None = None,
        target_role: str | None = None,
    ) -> Any:
        self.calls.append((created_by_user_id, advertisement_id))
        return SimpleNamespace(id=1, expected_total=42)


def _callback(signer: CallbackSigner, section: str, action: str) -> Any:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_panel(section, action)
    callback.message = AsyncMock(spec=Message)
    callback.message.chat = SimpleNamespace(id=10)
    callback.message.message_id = 20
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


async def _navigate(
    callback: Any,
    panel: ParsedPanel,
    user: UserSnapshot,
    signer: CallbackSigner,
    state: Any = None,
) -> None:
    await panel_navigate(
        callback,
        panel,
        _session(),
        user,
        state or _state(),
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

    async def get(self, key: str) -> Any:
        return 10


async def _write(
    callback: Any, panel: ParsedPanel, settings: _FakeSettingsRW, state: Any = None
) -> None:
    await panel_write(
        callback,
        panel,
        _session(),
        _user(),
        state or _state(),
        lambda s: _FakeUsersRW(),
        lambda s: settings,
        lambda s: _FakeAdmin(),
        lambda s: _FakeAds(),
        lambda s: _FakeBroadcasts(),
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
        _state(),
        lambda s: users,
        lambda s: _FakeSettingsRW(),
        lambda s: _FakeAdmin(),
        lambda s: _FakeAds(),
        lambda s: _FakeBroadcasts(),
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
        _state(),
        lambda s: users,
        lambda s: _FakeSettings(),
        lambda s: _FakeAds(),
        lambda s: _FakeAdmin(),
        _FakeQueue(),
        signer,
    )
    assert "555" in callback.message.edit_text.await_args.args[0]


# --- write stub (broadcast section still pending) -------------------------
async def test_write_stub_acks_for_pending_section() -> None:
    callback: Any = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    await _bwrite(callback, ParsedPanel("b", "cr"))  # broadcast create lands in 9.6.10
    callback.answer.assert_awaited_once()
    assert _call(callback.answer).args  # a toast message was supplied


# --- ads management (9.6.9) -----------------------------------------------
async def _bwrite(callback: Any, panel: ParsedPanel) -> None:
    await panel_write(
        callback,
        panel,
        _session(),
        _user(),
        _state(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeSettingsRW(),
        lambda s: _FakeAdmin(),
        lambda s: _FakeAds(),
        lambda s: _FakeBroadcasts(),
        _signer(),
    )


async def _awrite(
    callback: Any, panel: ParsedPanel, ads: _FakeAds, broadcasts: _FakeBroadcasts | None = None
) -> None:
    await panel_write(
        callback,
        panel,
        _session(),
        _user(),
        _state(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeSettingsRW(),
        lambda s: _FakeAdmin(),
        lambda s: ads,
        lambda s: broadcasts or _FakeBroadcasts(),
        _signer(),
    )


async def test_ad_disable_acts_directly() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "di")
    ads = _FakeAds()
    await _awrite(callback, ParsedPanel("a", "di", 1), ads)
    assert ("set_active", 1, False) in ads.calls
    assert "Disabled" in _call(callback.answer).args[0]


async def test_ad_delete_requires_confirm() -> None:
    signer = _signer()
    ads = _FakeAds()
    await _awrite(_callback(signer, "a", "de"), ParsedPanel("a", "de", 1), ads)
    assert all(c[0] != "delete" for c in ads.calls)  # not deleted yet
    callback = _callback(signer, "a", "dec")
    await _awrite(callback, ParsedPanel("a", "dec", 1), ads)
    assert ("delete", 1) in ads.calls
    assert "Deleted" in _call(callback.answer).args[0]


async def test_ad_broadcast_requires_confirm() -> None:
    signer = _signer()
    ads, casts = _FakeAds(), _FakeBroadcasts()
    await _awrite(_callback(signer, "a", "bc"), ParsedPanel("a", "bc", 1), ads, casts)
    assert casts.calls == []  # confirm screen only
    callback = _callback(signer, "a", "bcc")
    await _awrite(callback, ParsedPanel("a", "bcc", 1), ads, casts)
    assert casts.calls == [(1, 1)]  # (created_by user.id, ad_id)
    assert "42" in _call(callback.answer).args[0]


async def test_ad_action_without_target_hints() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "di")
    await _awrite(callback, ParsedPanel("a", "di", None), _FakeAds())
    assert "List" in _call(callback.answer).args[0]


async def test_ad_create_is_pending() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "cr")
    await _awrite(callback, ParsedPanel("a", "cr"), _FakeAds())
    assert "coming soon" in _call(callback.answer).args[0]


async def test_ads_list_renders_tappable_rows() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "ls")
    await _navigate(callback, ParsedPanel("a", "ls"), _user(), signer)
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    opened = {
        p.arg
        for row in markup.inline_keyboard
        for b in row
        if (p := signer.unpack_panel(b.callback_data)) is not None and p.action == "inf"
    }
    assert 1 in opened


async def test_ad_detail_renders_via_navigation() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "inf")
    await _navigate(callback, ParsedPanel("a", "inf", 1), _user(), signer)
    assert "Promo" in callback.message.edit_text.await_args.args[0]


async def test_ads_overall_stats_renders() -> None:
    signer = _signer()
    callback = _callback(signer, "a", "stt")
    await _navigate(callback, ParsedPanel("a", "stt"), _user(), signer)
    assert "Ad totals" in callback.message.edit_text.await_args.args[0]


# --- guided User Info lookup (9.6.8) --------------------------------------
async def test_user_info_arms_lookup_wizard() -> None:
    signer = _signer()
    callback = _callback(signer, "u", "inf")
    state = _state()
    await _navigate(callback, ParsedPanel("u", "inf", None), _user(), signer, state)
    state.set_state.assert_awaited_once()
    assert "Telegram ID" in callback.message.edit_text.await_args.args[0]


async def test_user_lookup_resolves_to_extended_detail() -> None:
    bot = AsyncMock()
    state = _state({"chat_id": 10, "message_id": 20})
    message: Any = AsyncMock(spec=Message)
    message.text = "555"
    await on_user_lookup(
        message,
        state,
        bot,
        _session(),
        _user(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeAdmin(),
        lambda s: _FakeSettings(),
        _signer(),
    )
    state.clear.assert_awaited_once()
    text = bot.edit_message_text.await_args.args[0]
    assert "User ID" in text and "555" in text and "History entries: 7" in text


async def test_user_lookup_non_numeric_keeps_state() -> None:
    bot = AsyncMock()
    state = _state({"chat_id": 10, "message_id": 20})
    message: Any = AsyncMock(spec=Message)
    message.text = "abc"
    message.reply = AsyncMock()
    await on_user_lookup(
        message,
        state,
        bot,
        _session(),
        _user(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeAdmin(),
        lambda s: _FakeSettings(),
        _signer(),
    )
    message.reply.assert_awaited_once()
    state.clear.assert_not_awaited()
    bot.edit_message_text.assert_not_awaited()


async def test_user_lookup_unknown_id_reports_not_found() -> None:
    bot = AsyncMock()
    state = _state({"chat_id": 10, "message_id": 20})
    message: Any = AsyncMock(spec=Message)
    message.text = "404"  # _FakeUsersRW only knows 555
    await on_user_lookup(
        message,
        state,
        bot,
        _session(),
        _user(),
        lambda s: _FakeUsersRW(),
        lambda s: _FakeAdmin(),
        lambda s: _FakeSettings(),
        _signer(),
    )
    assert "No user" in bot.edit_message_text.await_args.args[0]


# --- guided "Enter Value" for settings (9.6.7) ----------------------------
async def test_enter_value_arms_input_state() -> None:
    signer = _signer()
    callback = _callback(signer, "s", "ev")
    state = _state()
    await _write(callback, ParsedPanel("s", "ev", 0), _FakeSettingsRW(), state)
    state.set_state.assert_awaited_once()  # wizard armed
    assert "Send the new value" in callback.message.edit_text.await_args.args[0]


async def test_typed_value_shows_confirm_before_saving() -> None:
    bot = AsyncMock()
    state = _state({"field_index": 0, "chat_id": 10, "message_id": 20})
    message: Any = AsyncMock(spec=Message)
    message.text = "20"
    await on_setting_value(message, state, bot, _signer())
    state.clear.assert_awaited_once()
    bot.edit_message_text.assert_awaited_once()
    assert "Confirm" in bot.edit_message_text.await_args.args[0]


async def test_typed_non_numeric_keeps_state() -> None:
    bot = AsyncMock()
    state = _state({"field_index": 0, "chat_id": 10, "message_id": 20})
    message: Any = AsyncMock(spec=Message)
    message.text = "notanumber"
    message.reply = AsyncMock()
    await on_setting_value(message, state, bot, _signer())
    message.reply.assert_awaited_once()
    state.clear.assert_not_awaited()  # stays armed for the next attempt
    bot.edit_message_text.assert_not_awaited()


async def test_typed_out_of_range_keeps_state() -> None:
    bot = AsyncMock()
    state = _state({"field_index": 0, "chat_id": 10, "message_id": 20})  # worker_count max 32
    message: Any = AsyncMock(spec=Message)
    message.text = "999"
    message.reply = AsyncMock()
    await on_setting_value(message, state, bot, _signer())
    message.reply.assert_awaited_once()
    state.clear.assert_not_awaited()
