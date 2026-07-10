"""Redis cache adapter (MASTER_PLAN Task 3.2, Component RedisCache 9.5).

Implements ``CacheProtocol`` primitives. Keys are supplied by callers but are always
built via ``core.redis_keys.RedisKeys`` (this adapter never invents keys).
"""

from __future__ import annotations

import redis.asyncio as aioredis


class RedisCache:
    """Primitive key/value operations over the cache database."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value: str | None = await self._client.get(key)
        return value

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        # Redis rejects a non-positive EX ("invalid expire time"); treat ttl<=0 as
        # "no expiry" so a 0/disabled TTL setting can never crash the caller.
        if ttl is not None and ttl <= 0:
            ttl = None
        await self._client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def incr_with_ttl(self, key: str, *, ttl: int) -> int:
        """Increment ``key``; set ``ttl`` only when the counter is first created."""
        count: int = await self._client.incr(key)
        if count == 1:
            await self._client.expire(key, ttl)
        return count
