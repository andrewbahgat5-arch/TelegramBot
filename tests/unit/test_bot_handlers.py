"""Unit tests for the start/help handlers (MASTER_PLAN Task 4.8, Sprint 11.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message

from bot.callbacks.factory import CallbackSigner
from bot.handlers.help import handle_help
from bot.handlers.start import handle_language_callback, handle_referral, handle_start
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


async def test_start_offers_change_language_button() -> None:
    message = _message()
    await handle_start(message, _cmd(), translate, "en", _SIGNER, None)
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    button = keyboard.inline_keyboard[0][0]
    assert button.text == translate("language.change_button", "en")


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


async def test_language_pick_persists_and_confirms_in_new_locale() -> None:
    callback = _callback(_SIGNER.pack_language("ar"))
    repo = FakeUserRepo()
    repo.by_tid[1] = FakeUser(id=1, telegram_id=1, language="en")
    user = UserSnapshot.from_row(repo.by_tid[1])

    await handle_language_callback(
        callback, translate, "en", _SIGNER, lambda s: _user_service(repo), object(), user
    )

    assert repo.by_tid[1].language == "ar"
    confirmation = callback.message.edit_text.await_args.args[0]
    assert confirmation == translate("language.updated", "ar", native_name="العربية")


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
