"""Reliable-queue crash recovery (QueueService.recover_inflight).

A worker that dies after ``dequeue`` but before ``ack`` leaves the job stranded in
the in-flight set; ``recover_inflight`` (run once at startup) must re-drive it so its
``active_downloads`` slot stops blocking retries with "already being prepared".
"""

from __future__ import annotations

from services.queue_service import QueueService
from tests.unit._fakes import FakeQueueBackend


async def test_recover_inflight_requeues_stranded_jobs() -> None:
    backend = FakeQueueBackend()
    queue = QueueService(backend)
    await queue.enqueue("job-A")
    await queue.enqueue("job-B")

    # Two workers dequeue both jobs, then "crash" before acking → both in-flight.
    assert await queue.dequeue() == "job-A"
    assert await queue.dequeue() == "job-B"
    assert await queue.depth() == 0
    assert await queue.active_count() == 2

    recovered = await queue.recover_inflight()

    assert recovered == 2
    assert await queue.active_count() == 0  # in-flight set cleared
    assert await queue.depth() == 2  # both re-driven into the pending queue
    # They are dequeuable again (would otherwise be stuck forever).
    assert {await queue.dequeue(), await queue.dequeue()} == {"job-A", "job-B"}


async def test_recover_inflight_is_noop_when_nothing_in_flight() -> None:
    queue = QueueService(FakeQueueBackend())
    await queue.enqueue("job-A")
    assert await queue.recover_inflight() == 0
    assert await queue.depth() == 1
