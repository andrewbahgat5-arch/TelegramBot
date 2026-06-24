"""DownloadWorker (MASTER_PLAN Component 9.3, Task 6.6).

Pulls jobs from the queue and runs ``DownloadService`` to completion, owning the
unit of work (one DB transaction per job) and the retry / permanent-failure
decision (Section 12.3). The worker layer may import only ``services``, ``domain``,
``core`` (Section 8.1): it never touches repositories or the queue Redis client
directly — those arrive as injected factories from ``workers/main.py``.

Retry is the job-level state-machine retry the Sprint 6 validation checklist
specifies (``retry_queued`` → up to ``max_retries`` → ``permanently_failed``),
implemented by re-enqueuing at LOW priority. (In-process ``tenacity`` backoff —
pre-approved in Section 6.2 but not yet vendored — is deferred to a later sprint.)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.constants import PRIORITY_LOW
from core.logging import get_logger
from services.download_service import RETRYABLE_ERRORS, DownloadService
from services.queue_service import QueueService

_log = get_logger("workers.download_worker")

BuildDownloadService = Callable[[AsyncSession], DownloadService]


class DownloadWorker:
    def __init__(
        self,
        *,
        queue_service: QueueService,
        session_factory: async_sessionmaker[AsyncSession],
        build_download_service: BuildDownloadService,
        max_retries: int,
        idle_sleep_seconds: float = 1.0,
    ) -> None:
        self._queue = queue_service
        self._session_factory = session_factory
        self._build = build_download_service
        self._max_retries = max_retries
        self._idle_sleep = idle_sleep_seconds

    async def run_once(self) -> bool:
        """Process at most one job. Returns True if a job was handled."""
        job_id = await self._queue.dequeue()
        if job_id is None:
            return False
        await self._handle(job_id)
        return True

    async def run_forever(self) -> None:  # pragma: no cover - exercised via run_once
        _log.info("download_worker_started", max_retries=self._max_retries)
        while True:
            handled = await self.run_once()
            if not handled:
                await asyncio.sleep(self._idle_sleep)

    async def _handle(self, job_id: str) -> None:
        failure: Exception | None = None
        try:
            async with self._session_factory() as session:
                service = self._build(session)
                await service.process(job_id)
                await session.commit()
        except Exception as exc:  # boundary: classify + record, never crash the worker loop
            failure = exc
            _log.warning("job_processing_failed", job_id=job_id, error=str(exc))

        if failure is not None:
            await self._on_failure(job_id, failure)
        await self._queue.ack(job_id)

    async def _on_failure(self, job_id: str, exc: Exception) -> None:
        retryable = isinstance(exc, RETRYABLE_ERRORS)
        async with self._session_factory() as session:
            service = self._build(session)
            requeued = await service.handle_failure(
                job_id, reason=str(exc), retryable=retryable, max_retries=self._max_retries
            )
            await session.commit()
        if requeued:
            await self._queue.enqueue(job_id, priority=PRIORITY_LOW)
