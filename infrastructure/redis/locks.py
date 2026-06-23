"""Distributed lock (MASTER_PLAN Task 3.3, Section 11.4 ``lock:*``).

``SET key token NX PX ttl`` acquires; release is a token-compare-and-delete Lua
script so one holder can never release another's lock (foreign-release rejection).
"""

from __future__ import annotations

import redis.asyncio as aioredis

from core.uuid7 import uuid7_str

# Atomic compare-and-delete: only delete if the stored token matches ours.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class RedisLock:
    """Token-tagged distributed lock over the cache database."""

    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    async def acquire(self, key: str, *, ttl: int) -> str | None:
        """Acquire ``key`` for ``ttl`` seconds; return a release token or None."""
        token = uuid7_str()
        acquired = await self._client.set(key, token, nx=True, ex=ttl)
        return token if acquired else None

    async def release(self, key: str, token: str) -> bool:
        """Release ``key`` only if ``token`` matches the current holder."""
        result = await self._client.eval(_RELEASE_SCRIPT, 1, key, token)  # type: ignore[misc]
        return bool(result)
