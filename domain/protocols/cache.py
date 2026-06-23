"""Cache and lock protocols (MASTER_PLAN Task 3.2, 3.3; Component 9.5).

Low-level ports implemented by ``infrastructure/redis``. The service layer depends
on these, never on the Redis client directly. Keys are plain strings but must be
produced by ``core.redis_keys.RedisKeys`` — callers never hand-build keys.
"""

from __future__ import annotations

from typing import Protocol


class CacheProtocol(Protocol):
    """Primitive key/value cache operations (Section 11.4 keys)."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def incr_with_ttl(self, key: str, *, ttl: int) -> int:
        """Increment a counter, setting ``ttl`` on first creation. Returns the count."""
        ...


class LockProtocol(Protocol):
    """Distributed lock with token-tagged release (Section 11.4 ``lock:*``)."""

    async def acquire(self, key: str, *, ttl: int) -> str | None:
        """Acquire ``key`` for ``ttl`` seconds. Returns a release token, or None if held."""
        ...

    async def release(self, key: str, token: str) -> bool:
        """Release only if ``token`` matches the holder. Returns whether it was released."""
        ...
