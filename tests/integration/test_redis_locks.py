"""Integration tests for RedisLock (MASTER_PLAN Task 3.3)."""

from __future__ import annotations

import pytest

from core.redis_keys import RedisKeys
from infrastructure.redis.client import RedisClients
from infrastructure.redis.locks import RedisLock

pytestmark = pytest.mark.asyncio


async def test_acquire_blocks_second_acquire(redis_clients: RedisClients) -> None:
    lock = RedisLock(redis_clients.cache)
    key = RedisKeys.download_lock(1, "video", "720p")
    token = await lock.acquire(key, ttl=60)
    assert token is not None
    # A second client cannot acquire the held lock.
    assert await lock.acquire(key, ttl=60) is None


async def test_release_with_correct_token(redis_clients: RedisClients) -> None:
    lock = RedisLock(redis_clients.cache)
    key = RedisKeys.download_lock(2, "audio", "best")
    token = await lock.acquire(key, ttl=60)
    assert token is not None
    assert await lock.release(key, token) is True
    # After release the lock is free again.
    assert await lock.acquire(key, ttl=60) is not None


async def test_foreign_release_rejected(redis_clients: RedisClients) -> None:
    lock = RedisLock(redis_clients.cache)
    key = RedisKeys.download_lock(3, "video", "1080p")
    token = await lock.acquire(key, ttl=60)
    assert token is not None
    # A wrong token must not release someone else's lock.
    assert await lock.release(key, "not-the-token") is False
    # The real holder still holds it.
    assert await lock.acquire(key, ttl=60) is None
