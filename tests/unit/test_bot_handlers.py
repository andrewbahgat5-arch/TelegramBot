"""Unit tests for the start/help handlers (MASTER_PLAN Task 4.8, Sprint 11.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message

from bot.callbacks.factory import CallbackSigner
from bot.handlers.help import handle_help
from bot.handlers.start import handle_language_callback, handle_start
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


async def test_start_greets_by_name() -> None:
    message = _message()
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1, first_name="Trinity"))
    await handle_start(message, translate, "en", _SIGNER, user)
    text = message.answer.await_args.args[0]
    assert "Trinity" in text


async def test_start_without_user_still_replies() -> None:
    message = _message()
    await handle_start(message, translate, "en", _SIGNER, None)
    message.answer.assert_awaited_once()


async def test_start_offers_change_language_button() -> None:
    message = _message()
    await handle_start(message, translate, "en", _SIGNER, None)
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
