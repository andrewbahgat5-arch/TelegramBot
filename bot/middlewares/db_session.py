"""DbSessionMiddleware (MASTER_PLAN Component 9.1, Task 4.4).

Opens one async session per Telegram update, exposes it as ``data["session"]``,
commits on success and rolls back on any exception (Section 4.2.6: every persistent
mutation is committed or undone as a unit). Repositories never commit; this is the
unit-of-work boundary for the bot process (Section 8.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result
