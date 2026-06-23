"""Queue protocol (MASTER_PLAN Task 3.4; Component 9.5, Section 12).

A single priority queue (``queue:jobs`` sorted set) with an in-flight set
(``queue:active``). Lower score sorts first (Section 12.2). Implemented by
``infrastructure/redis/queue.py``.
"""

from __future__ import annotations

from typing import Protocol


class QueueProtocol(Protocol):
    async def enqueue(self, member: str, *, score: float) -> None:
        """Add ``member`` to the priority queue with the given score (lower = sooner)."""
        ...

    async def dequeue(self) -> str | None:
        """Atomically pop the lowest-score member and move it to the active set.

        Returns the member, or None if the queue is empty.
        """
        ...

    async def ack(self, member: str) -> None:
        """Remove ``member`` from the active set once processing completes."""
        ...

    async def depth(self) -> int:
        """Number of jobs waiting in the queue."""
        ...

    async def active_count(self) -> int:
        """Number of jobs currently in flight."""
        ...
