"""SettingsService (MASTER_PLAN Component 9.2, Task 3.6).

Read-through Redis cache over the ``settings`` table with type casting from the
stored ``value_type`` (Section 10.11) and write-through invalidation (Section 11.3).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import orjson

from core.redis_keys import RedisKeys
from domain.exceptions import AppError
from domain.protocols.cache import CacheProtocol
from domain.protocols.repositories import SettingsStoreProtocol


class SettingNotFoundError(AppError):
    """Raised when a requested settings key does not exist."""


class InvalidSettingValueError(AppError):
    """Raised when a new settings value does not parse as the key's ``value_type``."""


@dataclass(frozen=True, slots=True)
class SettingView:
    """A settings row for admin display (``/settings`` listing)."""

    key: str
    value: str
    value_type: str


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

    async def list_all(self) -> list[SettingView]:
        """Every settings key for the admin ``/settings`` listing."""
        rows: Sequence[Any] = await self._store.list_all()
        return [SettingView(r.key, r.value, r.value_type) for r in rows]

    async def get_view(self, key: str) -> SettingView | None:
        """One settings row as a display view (admin ``PUT`` echo), or None if absent."""
        row = await self._store.get_by_key(key)
        return None if row is None else SettingView(row.key, row.value, row.value_type)

    async def set_validated(self, key: str, value: str, *, updated_by: int | None = None) -> Any:
        """Validate ``value`` against the **existing** key's ``value_type``, then persist.

        Rejects unknown keys — the settings set is LOCKED (§13.4), so ``/setting_set``
        may only update keys that already exist, never invent one. Rejects a value that
        does not parse as the key's declared type. Returns the typed value on success.
        """
        row = await self._store.get_by_key(key)
        if row is None:
            raise SettingNotFoundError(f"unknown setting: {key}")
        typed = _validate(value, row.value_type)
        await self._store.upsert(key, value, updated_by=updated_by)
        await self._cache.delete(RedisKeys.setting(key))
        return typed


_TRUE = frozenset({"true", "1", "yes", "on"})
_BOOL_TOKENS = _TRUE | frozenset({"false", "0", "no", "off"})


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


def _validate(value: str, value_type: str) -> Any:
    """Like ``_cast`` but raises :class:`InvalidSettingValueError` on bad input.

    ``_cast`` trusts the stored value (already validated on write); this guards the
    write path, where ``/setting_set`` input is untrusted (Task 8.2 validation item).
    """
    try:
        if value_type == "bool":
            if value.strip().lower() not in _BOOL_TOKENS:
                raise ValueError(f"not a boolean: {value!r}")
            return value.strip().lower() in _TRUE
        return _cast(value, value_type)
    except (ValueError, orjson.JSONDecodeError) as exc:
        raise InvalidSettingValueError(f"{value!r} is not a valid {value_type}") from exc
