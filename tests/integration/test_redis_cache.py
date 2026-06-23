"""Integration tests for RedisCache + CacheService (MASTER_PLAN Task 3.2, 3.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import Settings
from infrastructure.redis.cache import RedisCache
from infrastructure.redis.client import RedisClients
from infrastructure.redis.locks import RedisLock
from services.cache_service import CacheService

pytestmark = pytest.mark.asyncio

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _cache_service(clients: RedisClients) -> CacheService:
    settings = Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]
    return CacheService(RedisCache(clients.cache), RedisLock(clients.cache), settings)


async def test_file_id_round_trip(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    assert await svc.get_file_id(42, "video", "720p") is None
    await svc.set_file_id(42, "video", "720p", "AgADfile123")
    assert await svc.get_file_id(42, "video", "720p") == "AgADfile123"
    await svc.delete_file_id(42, "video", "720p")
    assert await svc.get_file_id(42, "video", "720p") is None


async def test_metadata_dict_round_trip(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    payload = {"title": "Song", "duration": 211, "formats": ["video", "audio"]}
    await svc.set_metadata("youtube", "abc", payload)
    assert await svc.get_metadata("youtube", "abc") == payload


async def test_user_cache_round_trip_and_delete(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    await svc.set_user(123, {"id": 5, "role": "user"})
    assert await svc.get_user(123) == {"id": 5, "role": "user"}
    await svc.delete_user(123)
    assert await svc.get_user(123) is None


async def test_message_counter_increments_with_ttl(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    assert await svc.incr_message_count(7, ttl=60) == 1
    assert await svc.incr_message_count(7, ttl=60) == 2
    ttl = await redis_clients.cache.ttl("rate:msg:7")
    assert 0 < ttl <= 60


async def test_cooldown_flag(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    assert await svc.is_on_cooldown(9) is False
    await svc.set_cooldown(9, ttl=30)
    assert await svc.is_on_cooldown(9) is True


async def test_keys_follow_section_11_4_scheme(redis_clients: RedisClients) -> None:
    svc = _cache_service(redis_clients)
    await svc.set_file_id(1, "video", "720p", "fid")
    assert await redis_clients.cache.exists("fileid:1:video:720p") == 1
