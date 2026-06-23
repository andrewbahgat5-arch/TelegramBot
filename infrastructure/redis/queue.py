"""Redis priority queue adapter (MASTER_PLAN Task 3.4, Section 12).

A sorted set ``queue:jobs`` holds queued members scored by priority (lower sorts
first, Section 12.2). Dequeue is a Lua script that atomically pops the lowest-score
member and moves it to the ``queue:active`` set, so two workers can never receive
the same job.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from core.redis_keys import RedisKeys

# Atomic: pop lowest-score member from the queue, add it to the active set.
_DEQUEUE_SCRIPT = """
local popped = redis.call('ZPOPMIN', KEYS[1], 1)
if popped[1] == nil then
    return nil
end
redis.call('SADD', KEYS[2], popped[1])
return popped[1]
"""


class RedisQueue:
    """Priority queue over the queue database."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def enqueue(self, member: str, *, score: float) -> None:
        await self._client.zadd(RedisKeys.QUEUE_JOBS, {member: score})

    async def dequeue(self) -> str | None:
        result = await self._client.eval(  # type: ignore[misc]
            _DEQUEUE_SCRIPT, 2, RedisKeys.QUEUE_JOBS, RedisKeys.QUEUE_ACTIVE
        )
        return result if result is None else str(result)

    async def ack(self, member: str) -> None:
        await self._client.srem(RedisKeys.QUEUE_ACTIVE, member)  # type: ignore[misc]

    async def depth(self) -> int:
        count: int = await self._client.zcard(RedisKeys.QUEUE_JOBS)
        return count

    async def active_count(self) -> int:
        count: int = await self._client.scard(RedisKeys.QUEUE_ACTIVE)  # type: ignore[misc]
        return count
