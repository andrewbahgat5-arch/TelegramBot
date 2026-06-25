"""Worker heartbeat registry (MASTER_PLAN Task 10.4 / 10.5, Section 21).

Each worker loop writes ``worker:heartbeat:{worker_id}`` with a TTL of
``2x WORKER_HEARTBEAT_INTERVAL`` (Section 21), so a crashed worker's key expires
on its own. The api process reads the live count for the ``active_workers`` gauge
and the ``/v1/ready`` worker-presence check; the cleanup worker uses the same view
to detect stale workers whose in-flight jobs must be re-queued.
"""

from __future__ import annotations

import time

import redis.asyncio as aioredis

from core.redis_keys import RedisKeys

_SCAN_MATCH = "worker:heartbeat:*"


class WorkerHeartbeat:
    """Read/write worker liveness heartbeats over a Redis client."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def beat(self, worker_id: str, *, ttl_seconds: int) -> None:
        """Refresh this worker's heartbeat, expiring after ``ttl_seconds``."""
        await self._client.set(
            RedisKeys.worker_heartbeat(worker_id), str(time.time()), ex=ttl_seconds
        )

    async def count_active(self) -> int:
        """Count workers with a live (unexpired) heartbeat."""
        count = 0
        async for _ in self._client.scan_iter(match=_SCAN_MATCH):
            count += 1
        return count

    async def list_active(self) -> list[str]:
        """Return the worker ids with a live heartbeat (without the key prefix)."""
        prefix = RedisKeys.worker_heartbeat("")
        ids: list[str] = []
        async for key in self._client.scan_iter(match=_SCAN_MATCH):
            ids.append(key[len(prefix) :] if key.startswith(prefix) else key)
        return ids
