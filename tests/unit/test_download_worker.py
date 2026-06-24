"""Unit tests for the DownloadWorker loop + retry decision (MASTER_PLAN Task 6.6)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from domain.protocols.downloader import ProviderRetryElsewhere
from services.queue_service import QueueService
from tests.unit._fakes import FakeQueueBackend
from workers.download_worker import DownloadWorker


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:  # pragma: no cover - context manager handles it
        pass


@asynccontextmanager
async def _session_cm() -> Any:
    yield _FakeSession()


def _session_factory() -> Any:
    return _session_cm()


class _StubService:
    """Stands in for DownloadService: scripts process()/handle_failure()."""

    def __init__(self, *, error: Exception | None = None, requeue: bool = False) -> None:
        self._error = error
        self._requeue = requeue
        self.processed: list[str] = []
        self.failures: list[tuple[str, bool]] = []

    async def process(self, job_id: str) -> None:
        self.processed.append(job_id)
        if self._error is not None:
            raise self._error

    async def handle_failure(
        self, job_id: str, *, reason: str, retryable: bool, max_retries: int
    ) -> bool:
        self.failures.append((job_id, retryable))
        return self._requeue


def _worker(backend: FakeQueueBackend, service: _StubService) -> DownloadWorker:
    return DownloadWorker(
        queue_service=QueueService(backend),
        session_factory=_session_factory,  # type: ignore[arg-type]
        build_download_service=lambda _s: service,  # type: ignore[arg-type, return-value]
        max_retries=3,
    )


async def test_run_once_empty_queue_returns_false() -> None:
    worker = _worker(FakeQueueBackend(), _StubService())
    assert await worker.run_once() is False


async def test_success_processes_and_acks() -> None:
    backend = FakeQueueBackend()
    await backend.enqueue("job-1", score=1.0)
    service = _StubService()
    worker = _worker(backend, service)

    assert await worker.run_once() is True
    assert service.processed == ["job-1"]
    assert await backend.depth() == 0
    assert await backend.active_count() == 0  # acked


async def test_retryable_failure_requeues() -> None:
    backend = FakeQueueBackend()
    await backend.enqueue("job-1", score=1.0)
    service = _StubService(error=ProviderRetryElsewhere("x"), requeue=True)
    worker = _worker(backend, service)

    await worker.run_once()

    assert service.failures == [("job-1", True)]
    assert await backend.depth() == 1  # re-enqueued at LOW priority
    assert await backend.active_count() == 0  # original entry acked


async def test_permanent_failure_does_not_requeue() -> None:
    backend = FakeQueueBackend()
    await backend.enqueue("job-1", score=1.0)
    service = _StubService(error=ValueError("boom"), requeue=False)
    worker = _worker(backend, service)

    await worker.run_once()

    assert service.failures == [("job-1", False)]  # ValueError is not retryable
    assert await backend.depth() == 0
