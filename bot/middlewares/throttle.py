"""ThrottleMiddleware (MASTER_PLAN Component 9.1, Task 4.6).

Enforces the per-user message rate limit (``rate_limit_messages_per_minute``,
Section 14.5). Runs after ``AuthMiddleware`` (needs ``data["user"]``) and uses the
per-update session to build the ``RateLimitService``. Over-limit updates get a
friendly message and the handler is skipped.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from domain.exceptions import RateLimitExceededError
from services.rate_limit_service import RateLimitService

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
RateLimitServiceFactory = Callable[[AsyncSession], RateLimitService]

THROTTLE_MESSAGE = "Too many requests. Please slow down."


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate_limit_service_factory: RateLimitServiceFactory) -> None:
        self._rate_limit_service_factory = rate_limit_service_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("user")
        if user is None:  # unauthenticated update (e.g. banned, or no from_user)
            return await handler(event, data)

        service = self._rate_limit_service_factory(data["session"])
        try:
            await service.check_message_rate(user.id)
        except RateLimitExceededError:
            await _reply_throttled(event)
            return None
        return await handler(event, data)


async def _reply_throttled(event: TelegramObject) -> None:
    if isinstance(event, Message):
        await event.answer(THROTTLE_MESSAGE)
    elif isinstance(event, CallbackQuery):
        await event.answer(THROTTLE_MESSAGE, show_alert=True)
