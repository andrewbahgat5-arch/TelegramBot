"""Session-owning cookie repository adapter.

The cookie pool is a **process singleton** (it lives inside the provider, which the
registry holds for the process lifetime), but repositories are **session-scoped**. This
adapter bridges the two by opening a short-lived session per call and committing it —
the same pattern ``AdEventRecorder`` and ``UserHealthStoreAdapter`` already use, so
cookie bookkeeping never joins, blocks or rolls back a request's transaction.
"""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from domain.entities.cookie import CookieEvent, CookieSnapshot, CookieVerdict
from domain.enums.cookie_health import CookieHealth
from infrastructure.database.repositories.youtube_cookie import YoutubeCookieRepository

_log = get_logger("infrastructure.cookies.repository_adapter")

_R = TypeVar("_R")


class CookieRepositoryAdapter:
    """Implements ``CookieRepositoryProtocol`` on its own sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def _run(
        self, work: Callable[[YoutubeCookieRepository], Awaitable[_R]]
    ) -> _R:
        async with self._sessions() as session:
            result = await work(YoutubeCookieRepository(session))
            await session.commit()
            return result

    async def list_all(self) -> list[CookieSnapshot]:
        return await self._run(lambda repo: repo.list_all())

    async def get(self, cookie_id: int) -> CookieSnapshot | None:
        return await self._run(lambda repo: repo.get(cookie_id))

    async def get_by_label(self, label: str) -> CookieSnapshot | None:
        return await self._run(lambda repo: repo.get_by_label(label))

    async def list_candidates(
        self, *, egress_id: str, now: datetime.datetime
    ) -> list[CookieSnapshot]:
        return await self._run(
            lambda repo: repo.list_candidates(egress_id=egress_id, now=now)
        )

    async def create(
        self,
        *,
        label: str,
        file_version: int,
        content_hash: str,
        created_by: int | None = None,
        egress_id: str | None = None,
    ) -> CookieSnapshot:
        return await self._run(
            lambda repo: repo.create(
                label=label,
                file_version=file_version,
                content_hash=content_hash,
                created_by=created_by,
                egress_id=egress_id,
            )
        )

    async def record_use(self, cookie_id: int, *, at: datetime.datetime) -> None:
        await self._run(lambda repo: repo.record_use(cookie_id, at=at))

    async def record_outcome(
        self,
        cookie_id: int,
        *,
        verdict: CookieVerdict,
        status: CookieHealth,
        cooldown_until: datetime.datetime | None,
        auth_failures: int,
        cooldown_cycles: int,
        at: datetime.datetime,
    ) -> None:
        await self._run(
            lambda repo: repo.record_outcome(
                cookie_id,
                verdict=verdict,
                status=status,
                cooldown_until=cooldown_until,
                auth_failures=auth_failures,
                cooldown_cycles=cooldown_cycles,
                at=at,
            )
        )

    async def set_status(
        self,
        cookie_id: int,
        *,
        status: CookieHealth,
        actor_user_id: int | None = None,
        reason: str = "",
    ) -> None:
        await self._run(
            lambda repo: repo.set_status(
                cookie_id, status=status, actor_user_id=actor_user_id, reason=reason
            )
        )

    async def set_egress(self, cookie_id: int, egress_id: str) -> None:
        await self._run(lambda repo: repo.set_egress(cookie_id, egress_id))

    async def replace_file(
        self,
        cookie_id: int,
        *,
        expected_version: int,
        new_version: int,
        content_hash: str,
        actor_user_id: int | None = None,
    ) -> bool:
        return await self._run(
            lambda repo: repo.replace_file(
                cookie_id,
                expected_version=expected_version,
                new_version=new_version,
                content_hash=content_hash,
                actor_user_id=actor_user_id,
            )
        )

    async def list_events(self, cookie_id: int, *, limit: int = 20) -> list[CookieEvent]:
        """Recent audit events, detached from the ORM so the caller never touches rows
        whose session has already closed."""
        rows = await self._run(lambda repo: repo.list_events(cookie_id, limit=limit))
        return [
            CookieEvent(
                created_at=r.created_at,
                event=r.event,
                to_status=r.to_status,
                reason=r.reason,
                actor_user_id=r.actor_user_id,
            )
            for r in rows
        ]

    async def add_event(
        self,
        cookie_id: int,
        *,
        event: str,
        from_status: CookieHealth | None = None,
        to_status: CookieHealth | None = None,
        reason: str = "",
        egress_id: str | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        await self._run(
            lambda repo: repo.add_event(
                cookie_id,
                event=event,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                egress_id=egress_id,
                actor_user_id=actor_user_id,
            )
        )
