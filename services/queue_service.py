"""QueueService (MASTER_PLAN Component 9.2, Task 3.5).

Thin wrapper over ``QueueProtocol`` that applies the priority-band scoring from
Section 12.2 (``score = base + unix_time_ms/1000``; lower sorts first).
"""

from __future__ import annotations

import time

from core.constants import PRIORITY_NORMAL, priority_score
from domain.protocols.queue import QueueProtocol


class QueueService:
    def __init__(self, queue: QueueProtocol) -> None:
        self._queue = queue

    async def enqueue(
        self, job_id: str, *, priority: int = PRIORITY_NORMAL, now_ms: int | None = None
    ) -> None:
        """Enqueue a job at the given priority band (default NORMAL)."""
        millis = now_ms if now_ms is not None else int(time.time() * 1000)
        await self._queue.enqueue(job_id, score=priority_score(priority, millis))

    async def dequeue(self) -> str | None:
        return await self._queue.dequeue()

    async def ack(self, job_id: str) -> None:
        await self._queue.ack(job_id)

    async def depth(self) -> int:
        return await self._queue.depth()

    async def active_count(self) -> int:
        return await self._queue.active_count()

    async def recover_inflight(self, *, now_ms: int | None = None) -> int:
        """Re-drive jobs a crashed worker left in-flight, at NORMAL priority.

        Call once at worker startup, before any worker begins dequeuing, so stranded
        in-flight jobs (and the ``active_downloads`` slots blocking their retries) are
        re-processed instead of stuck. Returns the number recovered.
        """
        millis = now_ms if now_ms is not None else int(time.time() * 1000)
        return await self._queue.recover_inflight(score=priority_score(PRIORITY_NORMAL, millis))
