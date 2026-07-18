"""Unit tests for the global error-handler backstop (bot/handlers/errors.py)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import ErrorEvent

from bot.handlers.errors import handle_update_error
from core.i18n import translate


def _event(
    *,
    message: object | None = None,
    callback: object | None = None,
    exception: Exception | None = None,
) -> ErrorEvent:
    update = SimpleNamespace(update_id=42, message=message, callback_query=callback)
    return ErrorEvent.model_construct(
        update=update, exception=exception or RuntimeError("boom")
    )


def _user(language_code: str | None = "en") -> SimpleNamespace:
    return SimpleNamespace(id=555, language_code=language_code)


async def test_message_error_replies_with_generic_apology() -> None:
    message = SimpleNamespace(from_user=_user("en"), answer=AsyncMock())
    await handle_update_error(_event(message=message))
    message.answer.assert_awaited_once_with(translate("errors.unexpected", "en"))


async def test_callback_error_answers_alert_in_client_locale() -> None:
    callback = SimpleNamespace(from_user=_user("ar"), answer=AsyncMock())
    await handle_update_error(_event(callback=callback))
    callback.answer.assert_awaited_once_with(
        translate("errors.unexpected", "ar"), show_alert=True
    )


async def test_failed_apology_never_propagates() -> None:
    # The user may have blocked the bot between the update and the reply — the
    # backstop must still swallow that and leave only the log entry.
    message = SimpleNamespace(
        from_user=_user(None), answer=AsyncMock(side_effect=RuntimeError("blocked"))
    )
    await handle_update_error(_event(message=message))  # must not raise


async def test_update_without_message_or_callback_only_logs() -> None:
    await handle_update_error(_event())  # must not raise
