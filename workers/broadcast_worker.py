"""BroadcastWorker (MASTER_PLAN Component 9.3, Task 8.1, flow 16.8).

Polls the durable ``broadcasts`` table for the oldest ``pending`` row and fans it out
to the matching audience in id-cursor chunks of ``broadcast_chunk_size``. Per chunk:
read the page (one session), send each message (no session held during network I/O),
then commit the ``total_sent`` / ``total_failed`` deltas in their own transaction — so
progress survives a crash and resumes from the durable counters. One recipient's
delivery failure is logged and counted, never aborting the broadcast.

Like ``DownloadWorker`` (Section 8.1) this worker imports only ``services``/``domain``/
``core``: repositories arrive as session-bound factories built by ``workers/main.py``.
"""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core import metrics
from core.logging import get_logger
from domain.protocols.advertising import AdSenderProtocol
from domain.protocols.file_sender import MessageSenderProtocol
from domain.protocols.repositories import (
    BroadcastRepositoryProtocol,
    UserRepositoryProtocol,
)
from services.ad_service import AdBroadcastPlan, AdService, deliver_plan

_log = get_logger("workers.broadcast_worker")

BuildBroadcastRepo = Callable[[AsyncSession], BroadcastRepositoryProtocol[Any]]
BuildUserRepo = Callable[[AsyncSession], UserRepositoryProtocol[Any]]
BuildAdService = Callable[[AsyncSession], AdService]


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class BroadcastWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        build_broadcast_repo: BuildBroadcastRepo,
        build_user_repo: BuildUserRepo,
        sender: MessageSenderProtocol,
        chunk_size: int,
        sleep_between_chunks: float = 0.0,
        idle_sleep_seconds: float = 5.0,
        ad_sender: AdSenderProtocol | None = None,
        build_ad_service: BuildAdService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._build_broadcast_repo = build_broadcast_repo
        self._build_user_repo = build_user_repo
        self._sender = sender
        self._chunk_size = max(1, chunk_size)
        self._sleep_between_chunks = sleep_between_chunks
        self._idle_sleep = idle_sleep_seconds
        self._ad_sender = ad_sender
        self._build_ad_service = build_ad_service

    async def run_once(self) -> bool:
        """Process at most one pending broadcast. Returns True if one was handled."""
        async with self._session_factory() as session:
            repo = self._build_broadcast_repo(session)
            # Due-poller (9.5.10): only picks up broadcasts whose scheduled_at is NULL or
            # already due. Scheduled-but-not-yet-due rows are left for a later poll.
            broadcast = await repo.get_next_pending(now=_now())
            if broadcast is None:
                return False
            broadcast_id: int = broadcast.id
            text: str = broadcast.message_text
            role: str | None = broadcast.target_role
            language: str | None = broadcast.target_language
            advertisement_id: int | None = broadcast.advertisement_id
            await repo.set_status(broadcast_id, "in_progress")
            await session.commit()

        plan = await self._prepare_ad(advertisement_id)
        await self._fan_out(broadcast_id, text, role, language, plan)
        return True

    async def _prepare_ad(self, advertisement_id: int | None) -> AdBroadcastPlan | None:
        """Resolve a linked ad into a reusable delivery plan once (Sprint 9.5)."""
        if advertisement_id is None or self._build_ad_service is None:
            return None
        async with self._session_factory() as session:
            return await self._build_ad_service(session).prepare_broadcast(advertisement_id)

    async def run_forever(self) -> None:  # pragma: no cover - thin loop over run_once
        _log.info("broadcast_worker_started", chunk_size=self._chunk_size)
        while True:
            handled = await self.run_once()
            if not handled:
                await asyncio.sleep(self._idle_sleep)

    async def _fan_out(
        self,
        broadcast_id: int,
        text: str,
        role: str | None,
        language: str | None,
        plan: AdBroadcastPlan | None = None,
    ) -> None:
        after_id = 0
        while True:
            async with self._session_factory() as session:
                page = list(
                    await self._build_user_repo(session).page_for_broadcast(
                        after_id=after_id, limit=self._chunk_size, role=role, language=language
                    )
                )
            if not page:
                break

            sent = failed = 0
            for user in page:
                after_id = max(after_id, user.id)
                try:
                    await self._deliver_one(user.telegram_id, text, plan)
                    sent += 1
                except Exception as exc:  # one recipient's failure must not abort the rest
                    failed += 1
                    _log.warning(
                        "broadcast_send_failed",
                        broadcast_id=broadcast_id,
                        user_id=user.id,
                        error=str(exc),
                    )

            if sent:
                metrics.record_broadcast_sent("ok", count=sent)
            if failed:
                metrics.record_broadcast_sent("failed", count=failed)

            async with self._session_factory() as session:
                await self._build_broadcast_repo(session).add_counts(
                    broadcast_id, sent=sent, failed=failed
                )
                await session.commit()

            if self._sleep_between_chunks:
                await asyncio.sleep(self._sleep_between_chunks)

        async with self._session_factory() as session:
            await self._build_broadcast_repo(session).set_status(
                broadcast_id, "completed", completed_at=_now()
            )
            await session.commit()
        _log.info("broadcast_completed", broadcast_id=broadcast_id)

    async def _deliver_one(self, telegram_id: int, text: str, plan: AdBroadcastPlan | None) -> None:
        """Deliver a plain-text broadcast or, when linked, copy the ad (Sprint 9.5)."""
        if plan is not None and self._ad_sender is not None:
            await deliver_plan(self._ad_sender, plan, telegram_id)
        else:
            await self._sender.send_message(telegram_id, text)
