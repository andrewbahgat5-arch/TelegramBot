"""Unit tests for the start/help handlers (MASTER_PLAN Task 4.8)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.types import Message

from bot.handlers.help import handle_help
from bot.handlers.start import handle_start
from domain.entities.user import UserSnapshot
from tests.unit._fakes import FakeUser


def _message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    return message


async def test_start_greets_by_name() -> None:
    message = _message()
    user = UserSnapshot.from_row(FakeUser(id=1, telegram_id=1, first_name="Trinity"))
    await handle_start(message, user)
    text = message.answer.await_args.args[0]
    assert "Trinity" in text


async def test_start_without_user_still_replies() -> None:
    message = _message()
    await handle_start(message, None)
    message.answer.assert_awaited_once()


async def test_help_replies() -> None:
    message = _message()
    await handle_help(message)
    message.answer.assert_awaited_once()
