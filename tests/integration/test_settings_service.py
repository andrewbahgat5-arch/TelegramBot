"""Integration tests for SettingsService (MASTER_PLAN Task 3.6)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repositories import SettingsRepository
from infrastructure.redis.cache import RedisCache
from infrastructure.redis.client import RedisClients
from services.settings_service import SettingNotFoundError, SettingsService

pytestmark = pytest.mark.asyncio


def _service(db_session: AsyncSession, redis_clients: RedisClients) -> SettingsService:
    return SettingsService(
        SettingsRepository(db_session), RedisCache(redis_clients.cache), cache_ttl=60
    )


async def test_get_casts_int_from_text(
    db_session: AsyncSession, redis_clients: RedisClients
) -> None:
    svc = _service(db_session, redis_clients)
    value = await svc.get("free_daily_limit")
    assert value == 10
    assert isinstance(value, int)


async def test_get_casts_bool_and_json(
    db_session: AsyncSession, redis_clients: RedisClients
) -> None:
    svc = _service(db_session, redis_clients)
    assert await svc.get("maintenance_mode") is False
    assert await svc.get("providers_enabled") == {"ytdlp": True}


async def test_read_through_cache_serves_stale_until_invalidated(
    db_session: AsyncSession, redis_clients: RedisClients
) -> None:
    store = SettingsRepository(db_session)
    svc = SettingsService(store, RedisCache(redis_clients.cache), cache_ttl=60)
    assert await svc.get("free_daily_limit") == 10  # populates cache
    # Change the DB directly (bypassing svc.set, so the cache is not invalidated).
    await store.upsert("free_daily_limit", "777")
    assert await svc.get("free_daily_limit") == 10  # served from cache


async def test_set_updates_db_and_invalidates_cache(
    db_session: AsyncSession, redis_clients: RedisClients
) -> None:
    svc = _service(db_session, redis_clients)
    assert await svc.get("free_daily_limit") == 10  # cache populated
    await svc.set("free_daily_limit", "99")
    # Cache was invalidated, so the next read reflects the new DB value.
    assert await svc.get("free_daily_limit") == 99


async def test_unknown_key_raises(db_session: AsyncSession, redis_clients: RedisClients) -> None:
    svc = _service(db_session, redis_clients)
    with pytest.raises(SettingNotFoundError):
        await svc.get("does_not_exist")
