"""UserHealthChecker (Sprint 13.5) — batch Telegram-API status detection.

Sweeps users and classifies each as active / blocked / deleted by probing the
Telegram API, then records the outcome via the user repository (``mark_active`` /
``mark_blocked`` / ``mark_deleted``, which also stamp ``status_checked_at``).

The service is **framework-free** (MASTER_PLAN §8 / SPRINT_13_PLAN §6): the actual
``bot.get_chat`` call and the aiogram exception → outcome mapping live behind the
:class:`ChatProber` protocol, implemented by a thin bot-layer adapter. This keeps
``services`` free of aiogram imports (import-linter) and makes the checker fully
unit-testable with a fake prober and fake store.
"""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from core.logging import get_logger

_log = get_logger("services.user_health")


class ProbeOutcome(StrEnum):
    """The classification of a single user's Telegram-API status probe."""

    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"
    ERROR = "error"


class ChatProber(Protocol):
    """Probes one user's status. Implemented in the bot layer over ``Bot.get_chat``."""

    async def probe(self, telegram_id: int) -> ProbeOutcome: ...


class UserHealthStore(Protocol):
    """The slice of the user repository the checker persists outcomes through."""

    async def count_all(self) -> int: ...
    async def get_unchecked_ids(self, *, limit: int = 100) -> list[int]: ...
    async def mark_active(self, telegram_id: int) -> None: ...
    async def mark_blocked(self, telegram_id: int) -> None: ...
    async def mark_deleted(self, telegram_id: int) -> None: ...


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Outcome counts and wall-clock duration of a health sweep (SPRINT_13_PLAN §13.5)."""

    total_checked: int
    active: int
    blocked: int
    deleted: int
    errors: int
    duration_seconds: float


ProgressCallback = Callable[[int, int], Awaitable[None]]


async def _default_sleep(delay: float) -> None:
    await asyncio.sleep(delay)


class UserHealthChecker:
    def __init__(
        self,
        *,
        prober: ChatProber,
        store: UserHealthStore,
        chunk_delay_seconds: float = 1.0,
        now: Callable[[], datetime.datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._prober = prober
        self._store = store
        self._chunk_delay = chunk_delay_seconds
        self._now = now or (lambda: datetime.datetime.now(datetime.UTC))
        self._sleep = sleep or _default_sleep

    async def check_batch(self, telegram_ids: list[int]) -> HealthReport:
        """Probe a fixed set of users, persisting each outcome; no inter-user delay."""
        started = self._now()
        active = blocked = deleted = errors = 0
        for telegram_id in telegram_ids:
            outcome = await self._prober.probe(telegram_id)
            if outcome is ProbeOutcome.ACTIVE:
                await self._store.mark_active(telegram_id)
                active += 1
            elif outcome is ProbeOutcome.BLOCKED:
                await self._store.mark_blocked(telegram_id)
                blocked += 1
            elif outcome is ProbeOutcome.DELETED:
                await self._store.mark_deleted(telegram_id)
                deleted += 1
            else:
                errors += 1  # left unmarked so it is retried on the next sweep
        return HealthReport(
            total_checked=len(telegram_ids),
            active=active,
            blocked=blocked,
            deleted=deleted,
            errors=errors,
            duration_seconds=(self._now() - started).total_seconds(),
        )

    async def check_all(
        self,
        *,
        batch_size: int = 25,
        progress_callback: ProgressCallback | None = None,
    ) -> HealthReport:
        """Full sweep of every user in ``batch_size`` chunks with a delay between chunks.

        Chunks are drawn oldest-checked-first (``get_unchecked_ids``); a ``seen`` set
        guards against re-probing the same user within one sweep once its
        ``status_checked_at`` is stamped. Stops when everyone has been seen or a chunk
        yields no new ids. ``progress_callback(checked, total)`` fires after each chunk.
        """
        started = self._now()
        total = await self._store.count_all()
        seen: set[int] = set()
        active = blocked = deleted = errors = 0
        while len(seen) < total:
            ids = await self._store.get_unchecked_ids(limit=batch_size)
            fresh = [tid for tid in ids if tid not in seen]
            if not fresh:
                break
            report = await self.check_batch(fresh)
            seen.update(fresh)
            active += report.active
            blocked += report.blocked
            deleted += report.deleted
            errors += report.errors
            if progress_callback is not None:
                await progress_callback(len(seen), total)
            if len(seen) < total:
                await self._sleep(self._chunk_delay)
        _log.info(
            "user_health_sweep_complete",
            checked=len(seen),
            active=active,
            blocked=blocked,
            deleted=deleted,
            errors=errors,
        )
        return HealthReport(
            total_checked=len(seen),
            active=active,
            blocked=blocked,
            deleted=deleted,
            errors=errors,
            duration_seconds=(self._now() - started).total_seconds(),
        )
