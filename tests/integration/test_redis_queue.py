"""Integration tests for RedisQueue + QueueService (MASTER_PLAN Task 3.4, 3.5)."""

from __future__ import annotations

import asyncio

import pytest

from core.constants import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_NORMAL
from infrastructure.redis.client import RedisClients
from infrastructure.redis.queue import RedisQueue
from services.queue_service import QueueService

pytestmark = pytest.mark.asyncio


async def test_priority_ordering(redis_clients: RedisClients) -> None:
    svc = QueueService(RedisQueue(redis_clients.queue))
    # Same instant, different bands: HIGH (lower score) must come out first.
    await svc.enqueue("normal-job", priority=PRIORITY_NORMAL, now_ms=1000)
    await svc.enqueue("high-job", priority=PRIORITY_HIGH, now_ms=1000)
    await svc.enqueue("low-job", priority=PRIORITY_LOW, now_ms=1000)
    assert await svc.dequeue() == "high-job"
    assert await svc.dequeue() == "normal-job"
    assert await svc.dequeue() == "low-job"
    assert await svc.dequeue() is None


async def test_fifo_within_band(redis_clients: RedisClients) -> None:
    svc = QueueService(RedisQueue(redis_clients.queue))
    for i in range(5):
        await svc.enqueue(f"job-{i}", priority=PRIORITY_NORMAL, now_ms=1000 + i)
    out = [await svc.dequeue() for _ in range(5)]
    assert out == [f"job-{i}" for i in range(5)]


async def test_depth_active_and_ack(redis_clients: RedisClients) -> None:
    svc = QueueService(RedisQueue(redis_clients.queue))
    await svc.enqueue("j1", now_ms=1)
    await svc.enqueue("j2", now_ms=2)
    assert await svc.depth() == 2
    member = await svc.dequeue()
    assert member == "j1"
    assert await svc.depth() == 1
    assert await svc.active_count() == 1
    await svc.ack("j1")
    assert await svc.active_count() == 0


async def test_concurrent_dequeue_no_duplicates(redis_clients: RedisClients) -> None:
    svc = QueueService(RedisQueue(redis_clients.queue))
    total = 1000
    for i in range(total):
        await svc.enqueue(f"job-{i}", now_ms=i)

    async def drain() -> list[str]:
        collected: list[str] = []
        while (member := await svc.dequeue()) is not None:
            collected.append(member)
        return collected

    batches = await asyncio.gather(drain(), drain(), drain())
    seen = [m for batch in batches for m in batch]
    assert len(seen) == total
    assert len(set(seen)) == total  # no member dequeued twice
    assert await svc.depth() == 0
