"""Unit tests for the start/help handlers (MASTER_PLAN Task 4.8, Sprint 11.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from bot.callbacks.factory import CallbackSigner
from bot.handlers.help import handle_help
from bot.handlers.start import (
    handle_language_callback,
    handle_referral,
    handle_referral_callback,
    handle_start,
    handle_user_settings,
)
from core.i18n import translate
from domain.entities.user import UserSnapshot
from services.user_service import UserService
from tests.unit._fakes import FakeUser, FakeUserRepo, make_cache_service

_SIGNER = CallbackSigner("test-secret")


def _user_service(repo: FakeUserRepo) -> UserService:
    cache_service, _ = make_cache_service()
    return UserService(repo, cache_service, owner_telegram_id=999)


def _callback(data: str) -> AsyncMock:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    return message


def _cmd(args: str | None = None) -> CommandObject:
    return CommandObject(command="start", args=args)


class _FakeReferral:
    def __init__(self, *, result: object | None = None, stats: object | None = None) -> None:
        self._result = result
        self._stats = stats
        self.processed: list[tuple[str, int]] = []

    async def process_referral(self, code: str, new_user_id: int) -> object:
        self.processed.append((code, new_user_id))
        return self._result

    async def get_user_referral_stats(self, user_id: int) -> object:
        return self._stats


async def test_start_processes_referral_and_notifies_referrer() -> None:
    from services.referral_service import ReferralResult

    message = _message()
    message.bot = AsyncMock()
    user = UserSnapshot.from_row(FakeUser(id=2, telegram_id=200))
    referral = _FakeReferral(
        result=ReferralResult(
            success=True,
            reason="ok",
            referrer_telegram_id=100,
            referrer_total_referrals=3,
            reward_downloads=5,
        )
    )
    await handle_start(
        message,
        _cmd("ref_abc123"),
        translate,
        "en",
        _SIGNER,
        user,
        object(),  # session (factory ignores it)
        None,
        lambda s: referral,
    )
    assert referral.processed == [("abc123", 2)]
    message.bot.send_message.assert_awaited_once()
    assert message.bot.send_message.await_args.args[0] == 100


async def test_referral_screen_shows_link() -> None:
    from services.referral_service import UserReferralStats

    message = _message()
    user = UserSnapshot.from_row(FakeUser(id=2, telegram_id=200))
    stats = UserReferralStats(
        referral_code="abc123",
        referral_link="https://t.me/Bot?start=ref_abc123",
        total_invited=4,
        total_bonus_downloads=20,
    )
    await handle_referral(
        message, translate, "en", user, object(), lambda s: _FakeReferral(stats=stats), None
    )
    text = message.answer.await_args.args[0]
    assert "ref_abc123" in text and "4" in text


async def test_start_greets_by_name() -> None:
    message = _message()
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1, first_name="Trinity"))
    await handle_start(message, _cmd(), translate, "en", _SIGNER, user)
    text = message.answer.await_args.args[0]
    assert "Trinity" in text


async def test_start_without_user_still_replies() -> None:
    message = _message()
    await handle_start(message, _cmd(), translate, "en", _SIGNER, None)
    message.answer.assert_awaited_once()


async def test_start_offers_all_working_menu_buttons() -> None:
    # Item #9: Start shows the working buttons — My files, Settings, Try Premium, Change language.
    message = _message()
    await handle_start(message, _cmd(), translate, "en", _SIGNER, None)
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    labels = [b.text for row in keyboard.inline_keyboard for b in row]
    for key in (
        "start.button.my_files",
        "settings.open_button",
        "start.button.try_premium",
        "start.button.contact_us",
        "language.change_button",
    ):
        assert translate(key, "en") in labels
    # Contact-us is a URL button (opens the support account), not a callback.
    contact = next(
        b for row in keyboard.inline_keyboard for b in row
        if b.text == translate("start.button.contact_us", "en")
    )
    assert contact.url and contact.callback_data is None
    body = message.answer.await_args.args[0]
    assert "Features" in body and "How to use" in body  # the redesigned home text
    assert translate("start.contact_hint", "en") in body  # the bug/suggestion hint


async def test_help_replies() -> None:
    message = _message()
    await handle_help(message, translate, "en")
    message.answer.assert_awaited_once()


# --- Language picker / pick (Sprint 11.5) ----------------------------------
async def test_language_open_sentinel_shows_picker() -> None:
    callback = _callback(_SIGNER.pack_language(""))
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    user = UserSnapshot.from_row(repo.by_tid[1])

    await handle_language_callback(
        callback, translate, "en", _SIGNER, lambda s: _user_service(repo), object(), user
    )

    callback.message.edit_text.assert_awaited_once()
    text, kwargs = (
        callback.message.edit_text.await_args.args,
        callback.message.edit_text.await_args.kwargs,
    )
    assert text[0] == translate("language.picker_prompt", "en")
    assert kwargs["reply_markup"].inline_keyboard  # at least one language button
    assert repo.by_tid[1].language == "en"  # unchanged — this was just "open", not a pick


async def test_language_pick_persists_and_reopens_start_in_new_locale() -> None:
    # Item #7: a pick from Start persists, toasts the confirmation in the new locale, and
    # reopens the Start screen (in the new locale) instead of a dead-end confirmation.
    callback = _callback(_SIGNER.pack_language("ar"))  # legacy 3-part -> origin defaults to Start
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    user = UserSnapshot.from_row(repo.by_tid[1])

    await handle_language_callback(
        callback, translate, "en", _SIGNER, lambda s: _user_service(repo), object(), user
    )

    assert repo.by_tid[1].language == "ar"
    callback.answer.assert_awaited_with(translate("language.updated", "ar", native_name="العربية"))
    reopened = callback.message.edit_text.await_args.args[0]
    assert reopened.startswith(translate("start.welcome_anonymous", "ar"))  # Start, in Arabic
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert translate("language.change_button", "ar") in labels


# --- User Settings screen (item #10) ---------------------------------------
class _FakePrefService:
    def __init__(self) -> None:
        from services.user_preference_service import UserPreferences

        self.prefs = UserPreferences()
        self.toggled: list[int] = []

    async def get(self, user_id: int) -> object:
        return self.prefs

    async def toggle(self, user_id: int, index: int) -> object:
        self.toggled.append(index)
        return self.prefs


async def test_user_settings_open_renders_toggles() -> None:
    callback = _callback(_SIGNER.pack_user_setting(-1))  # -1 = open
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1))
    await handle_user_settings(
        callback, translate, "en", _SIGNER, object(), user, lambda s: _FakePrefService()
    )
    text = callback.message.edit_text.await_args.args[0]
    assert "Settings" in text
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("Auto-download" in lb for lb in labels)


async def test_user_settings_toggle_flips_the_pref() -> None:
    callback = _callback(_SIGNER.pack_user_setting(1))  # toggle index 1 (hide_title)
    prefs = _FakePrefService()
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1))
    await handle_user_settings(
        callback, translate, "en", _SIGNER, object(), user, lambda s: prefs
    )
    assert prefs.toggled == [1]  # the toggle was applied


async def test_user_settings_back_reopens_start() -> None:
    callback = _callback(_SIGNER.pack_user_setting(-2))  # -2 = back to Start
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1))
    await handle_user_settings(
        callback, translate, "en", _SIGNER, object(), user, lambda s: _FakePrefService()
    )
    text = callback.message.edit_text.await_args.args[0]
    assert text.startswith(translate("start.welcome_anonymous", "en"))  # Start home reopened


class _FakeReferralService:
    async def get_user_referral_stats(self, user_id: int) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(
            referral_link="https://t.me/bot?start=ref_abc", total_invited=3, total_bonus_downloads=6
        )


class _FakeReferralSettings:
    async def get(self, key: str) -> object:
        return True if key == "referral_enabled" else 5


async def test_referral_callback_renders_screen_with_back_button() -> None:
    # Item #9: the "Try Premium" button renders the referral screen in place, with a Back row.
    callback = _callback(_SIGNER.pack_referral())
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1))
    await handle_referral_callback(
        callback,
        translate,
        "en",
        _SIGNER,
        object(),
        user,
        lambda s: _FakeReferralService(),
        lambda s: _FakeReferralSettings(),
    )
    callback.message.edit_text.assert_awaited_once()
    kb = callback.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert translate("common.back", "en") in labels


async def test_language_pick_origin_survives_pack_unpack() -> None:
    # The picker's origin rides through the signed callback so the pick knows where to return.
    parsed = _SIGNER.unpack(_SIGNER.pack_language("ar", "p"))
    assert parsed is not None and parsed.language == "ar" and parsed.origin == "p"
    legacy = _SIGNER.unpack(_SIGNER.pack_language("ar"))  # 3-part -> no origin
    assert legacy is not None and legacy.language == "ar" and legacy.origin is None


async def test_language_pick_rejects_disabled_or_unknown_code() -> None:
    callback = _callback(_SIGNER.pack_language("fr"))  # not a discovered/enabled locale
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    user = UserSnapshot.from_row(repo.by_tid[1])

    await handle_language_callback(
        callback, translate, "en", _SIGNER, lambda s: _user_service(repo), object(), user
    )

    callback.message.edit_text.assert_not_awaited()
    assert repo.by_tid[1].language == "en"  # unchanged
    callback.answer.assert_awaited_once()


async def test_language_callback_forged_data_ignored() -> None:
    callback = _callback("l|en|deadbeef00")  # bad signature
    repo = FakeUserRepo()

    await handle_language_callback(
        callback,
        translate,
        "en",
        _SIGNER,
        lambda s: _user_service(repo),
        object(),
        UserSnapshot.from_row(FakeUser(id=1, telegram_id=1)),
    )

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_not_awaited()
