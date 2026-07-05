"""UserHealthStoreAdapter — session-owning store for UserHealthChecker (Sprint 13.5).

The health sweep is a long, on-demand operation, so it must not run inside the
request-bound session (that would hold one transaction open for the whole sweep).
This adapter opens a short-lived, committed session per operation over the injected
factory — mirroring :class:`AdEventRecorder` (D-052). It satisfies the
``services.user_health.UserHealthStore`` protocol *structurally* (no upward import,
so ``infrastructure`` stays a leaf per import-linter).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.database.repositories.user import UserRepository


class UserHealthStoreAdapter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def count_all(self) -> int:
        async with self._session_factory() as session:
            return await UserRepository(session).count_all()

    async def get_unchecked_ids(self, *, limit: int = 100) -> list[int]:
        async with self._session_factory() as session:
            return await UserRepository(session).get_unchecked_ids(limit=limit)

    async def mark_active(self, telegram_id: int) -> None:
        async with self._session_factory() as session:
            await UserRepository(session).mark_active(telegram_id)
            await session.commit()

    async def mark_blocked(self, telegram_id: int) -> None:
        async with self._session_factory() as session:
            await UserRepository(session).mark_blocked(telegram_id)
            await session.commit()

    async def mark_deleted(self, telegram_id: int) -> None:
        async with self._session_factory() as session:
            await UserRepository(session).mark_deleted(telegram_id)
            await session.commit()
