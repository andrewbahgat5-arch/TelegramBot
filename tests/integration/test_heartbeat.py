"""Integration tests for WorkerHeartbeat (MASTER_PLAN Task 10.4 / 10.5, Section 21)."""

from __future__ import annotations

import pytest

from infrastructure.redis.client import RedisClients
from infrastructure.redis.heartbeat import WorkerHeartbeat

pytestmark = pytest.mark.asyncio


async def test_beat_then_count_and_list(redis_clients: RedisClients) -> None:
    hb = WorkerHeartbeat(redis_clients.cache)
    assert await hb.count_active() == 0

    await hb.beat("host:100:0", ttl_seconds=60)
    await hb.beat("host:100:1", ttl_seconds=60)
    assert await hb.count_active() == 2
    assert set(await hb.list_active()) == {"host:100:0", "host:100:1"}


async def test_heartbeat_expires(redis_clients: RedisClients) -> None:
    hb = WorkerHeartbeat(redis_clients.cache)
    await hb.beat("host:200:0", ttl_seconds=1)
    assert await hb.count_active() == 1
    # The key carries a TTL; confirm it is set so a crashed worker self-evicts.
    ttl = await redis_clients.cache.ttl("worker:heartbeat:host:200:0")
    assert 0 < ttl <= 1
