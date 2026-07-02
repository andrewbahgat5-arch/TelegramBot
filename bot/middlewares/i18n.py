"""LocaleMiddleware (MASTER_PLAN Component 9.1, Sprint 11.5).

Resolves the effective locale for the current update and attaches it as
``data["locale"]``. Runs after ``AuthMiddleware`` (needs ``data["user"]``) and
before ``ThrottleMiddleware`` (its own reply also needs a resolved locale).

Resolution is read-only (``core.i18n.resolve_locale``): a user's stored
``users.language`` is never rewritten here, even if it currently points at a
disabled/unknown locale — see that function's docstring.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.i18n import resolve_locale
from domain.entities.user import UserSnapshot

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LocaleMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user: UserSnapshot | None = data.get("user")
        data["locale"] = resolve_locale(user.language if user is not None else None)
        return await handler(event, data)
