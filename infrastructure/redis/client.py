"""Redis connection management (MASTER_PLAN Task 3.1).

Two logical databases on the same Redis instance: cache (``REDIS_CACHE_DB``) and
queue (``REDIS_QUEUE_DB``). ``decode_responses=True`` so the rest of the code works
with ``str`` rather than ``bytes``.
"""

from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as aioredis

from core.config import Settings


@dataclass(frozen=True)
class RedisClients:
    """The cache and queue Redis clients for a process."""

    cache: aioredis.Redis
    queue: aioredis.Redis

    async def aclose(self) -> None:
        await self.cache.aclose()
        await self.queue.aclose()


def create_redis_clients(settings: Settings) -> RedisClients:
    """Build the cache and queue clients from configuration."""
    cache = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url,
        db=settings.redis_cache_db,
        decode_responses=True,
    )
    queue = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.redis_url,
        db=settings.redis_queue_db,
        decode_responses=True,
    )
    return RedisClients(cache=cache, queue=queue)
