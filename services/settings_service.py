"""SettingsService (MASTER_PLAN Component 9.2, Task 3.6).

Read-through Redis cache over the ``settings`` table with type casting from the
stored ``value_type`` (Section 10.11) and write-through invalidation (Section 11.3).
"""

from __future__ import annotations

from typing import Any

import orjson

from core.redis_keys import RedisKeys
from domain.exceptions import AppError
from domain.protocols.cache import CacheProtocol
from domain.protocols.repositories import SettingsStoreProtocol


class SettingNotFoundError(AppError):
    """Raised when a requested settings key does not exist."""


class SettingsService:
    def __init__(
        self,
        store: SettingsStoreProtocol,
        cache: CacheProtocol,
        *,
        cache_ttl: int = 60,
    ) -> None:
        self._store = store
        self._cache = cache
        self._cache_ttl = cache_ttl

    async def get(self, key: str) -> Any:
        """Return the typed value for ``key`` (read-through cache)."""
        cached = await self._cache.get(RedisKeys.setting(key))
        if cached is not None:
            payload = orjson.loads(cached)
            return _cast(payload["value"], payload["value_type"])

        row = await self._store.get_by_key(key)
        if row is None:
            raise SettingNotFoundError(f"unknown setting: {key}")

        await self._cache.set(
            RedisKeys.setting(key),
            orjson.dumps({"value": row.value, "value_type": row.value_type}).decode(),
            ttl=self._cache_ttl,
        )
        return _cast(row.value, row.value_type)

    async def set(self, key: str, value: str, *, updated_by: int | None = None) -> None:
        """Persist a new value and invalidate the cache (write-through)."""
        await self._store.upsert(key, value, updated_by=updated_by)
        await self._cache.delete(RedisKeys.setting(key))


_TRUE = frozenset({"true", "1", "yes", "on"})


def _cast(value: str, value_type: str) -> Any:
    if value_type == "int":
        return int(value)
    if value_type == "bool":
        return value.strip().lower() in _TRUE
    if value_type == "float":
        return float(value)
    if value_type == "json":
        return orjson.loads(value)
    return value
