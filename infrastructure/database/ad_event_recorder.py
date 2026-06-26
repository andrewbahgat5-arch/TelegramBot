"""AdEventRecorder — fire-and-forget ad-event writer (MASTER_PLAN Task 9.5.9, D-052).

Implements :class:`AdEventRecorderProtocol`. ``record_impression`` / ``record_click``
schedule a background task that writes one ``ad_events`` row on its **own** short-lived
session, then return immediately — so the analytics write is **off the ad delivery hot
path** and never adds latency to a download/ad send. Best-effort: a failed write (or no
running event loop) is logged and swallowed; the ``advertisements`` / ``ad_buttons``
counters stay the source of truth (D-045).

The recorder is a process singleton wired at the composition roots (it owns a session
factory, which the request-bound services must not). ``aclose`` awaits any in-flight
writes for a graceful shutdown.
"""

from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.logging import get_logger
from domain.enums import AdEventType
from infrastructure.database.repositories.ad_event import AdEventRepository

_log = get_logger("infrastructure.ad_event_recorder")


class AdEventRecorder:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._pending: set[asyncio.Task[None]] = set()

    def record_impression(
        self, *, advertisement_id: int, user_id: int | None, placement: str | None
    ) -> None:
        self._spawn(
            event_type=AdEventType.IMPRESSION.value,
            advertisement_id=advertisement_id,
            user_id=user_id,
            placement=placement,
            button_id=None,
        )

    def record_click(
        self, *, advertisement_id: int, user_id: int | None, button_id: int | None
    ) -> None:
        self._spawn(
            event_type=AdEventType.CLICK.value,
            advertisement_id=advertisement_id,
            user_id=user_id,
            placement=None,
            button_id=button_id,
        )

    async def aclose(self) -> None:
        """Await in-flight writes (best-effort) so a graceful shutdown doesn't drop them."""
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    def _spawn(
        self,
        *,
        event_type: str,
        advertisement_id: int,
        user_id: int | None,
        placement: str | None,
        button_id: int | None,
    ) -> None:
        coro = self._write(
            event_type=event_type,
            advertisement_id=advertisement_id,
            user_id=user_id,
            placement=placement,
            button_id=button_id,
        )
        try:
            task = asyncio.create_task(coro)
        except RuntimeError:
            # No running loop (e.g. called from sync context): analytics is best-effort.
            # Close the coroutine so it doesn't warn about never being awaited.
            coro.close()
            _log.warning("ad_event_no_running_loop", event_type=event_type, ad_id=advertisement_id)
            return
        self._pending.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._pending.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:  # boundary: an analytics write must never surface to the caller
            _log.warning("ad_event_write_failed", error=str(exc))

    async def _write(
        self,
        *,
        event_type: str,
        advertisement_id: int,
        user_id: int | None,
        placement: str | None,
        button_id: int | None,
    ) -> None:
        async with self._session_factory() as session:
            await AdEventRepository(session).record(
                event_type=event_type,
                advertisement_id=advertisement_id,
                user_id=user_id,
                placement=placement,
                button_id=button_id,
            )
            await session.commit()
