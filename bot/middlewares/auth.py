"""AuthMiddleware (MASTER_PLAN Component 9.1, Task 4.5).

Resolves the Telegram user to a ``users`` row (cache-first, D-014), records activity
(debounced), and rejects banned users with a friendly message before any handler
runs. The resolved :class:`UserSnapshot` is attached as ``data["user"]``.

Because repositories are bound to the per-update session, the middleware builds the
``UserService`` from a factory using ``data["session"]`` (set by
``DbSessionMiddleware``, which must run first).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from services.user_service import UserService

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
UserServiceFactory = Callable[[AsyncSession], UserService]

BAN_MESSAGE = "You are banned from using this bot."


class AuthMiddleware(BaseMiddleware):
    def __init__(self, user_service_factory: UserServiceFactory) -> None:
        self._user_service_factory = user_service_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None:  # service messages, etc. — nothing to authenticate
            return await handler(event, data)

        service = self._user_service_factory(data["session"])
        snapshot = await service.get_or_create_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            language=tg_user.language_code,
        )
        await service.record_activity(snapshot)

        if snapshot.is_banned:
            await _reply_banned(event)
            return None

        data["user"] = snapshot
        return await handler(event, data)


async def _reply_banned(event: TelegramObject) -> None:
    if isinstance(event, Message):
        await event.answer(BAN_MESSAGE)
    elif isinstance(event, CallbackQuery):
        await event.answer(BAN_MESSAGE, show_alert=True)
