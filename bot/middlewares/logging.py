"""LoggingMiddleware (MASTER_PLAN Component 9.1, Task 4.3).

Binds a fresh UUIDv7 correlation ID for the duration of one Telegram update so every
log line emitted while handling it carries the same ``correlation_id`` (Section 15.2).
The ID is also placed in the handler ``data`` for downstream use.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.logging import correlation_context
from core.sentry import request_scope
from core.uuid7 import uuid7_str

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        correlation_id = uuid7_str()
        data["correlation_id"] = correlation_id
        # Each update gets its own Sentry scope tagged with the correlation id, so a
        # captured exception is attributable to the originating request (Task 10.1).
        with request_scope(correlation_id=correlation_id), correlation_context(correlation_id):
            return await handler(event, data)
