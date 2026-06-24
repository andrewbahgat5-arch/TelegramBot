"""CacheService (MASTER_PLAN Component 9.2, Task 3.5).

The single, audited entry point for Redis cache + download-lock operations. Exposes
typed methods only — callers never pass raw key strings (exit criterion). Keys come
from ``core.redis_keys.RedisKeys``; dict values are serialized with orjson.
"""

from __future__ import annotations

from typing import Any

import orjson

from core.config import Settings
from core.redis_keys import RedisKeys
from domain.protocols.cache import CacheProtocol, LockProtocol


class CacheService:
    def __init__(self, cache: CacheProtocol, lock: LockProtocol, settings: Settings) -> None:
        self._cache = cache
        self._lock = lock
        self._settings = settings

    # --- file_id cache (authoritative source: cached_files) ---
    async def get_file_id(self, media_id: int, format_: str, quality: str) -> str | None:
        return await self._cache.get(RedisKeys.file_id(media_id, format_, quality))

    async def set_file_id(self, media_id: int, format_: str, quality: str, file_id: str) -> None:
        await self._cache.set(
            RedisKeys.file_id(media_id, format_, quality),
            file_id,
            ttl=self._settings.cache_fileid_ttl,
        )

    async def delete_file_id(self, media_id: int, format_: str, quality: str) -> None:
        await self._cache.delete(RedisKeys.file_id(media_id, format_, quality))

    # --- metadata cache ---
    async def get_metadata(self, platform: str, video_id: str) -> dict[str, Any] | None:
        raw = await self._cache.get(RedisKeys.metadata(platform, video_id))
        return None if raw is None else _loads(raw)

    async def set_metadata(self, platform: str, video_id: str, data: dict[str, Any]) -> None:
        await self._cache.set(
            RedisKeys.metadata(platform, video_id),
            _dumps(data),
            ttl=self._settings.cache_metadata_ttl,
        )

    # --- user cache (D-014) ---
    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        raw = await self._cache.get(RedisKeys.user(telegram_id))
        return None if raw is None else _loads(raw)

    async def set_user(self, telegram_id: int, data: dict[str, Any]) -> None:
        await self._cache.set(
            RedisKeys.user(telegram_id), _dumps(data), ttl=self._settings.cache_user_ttl
        )

    async def delete_user(self, telegram_id: int) -> None:
        await self._cache.delete(RedisKeys.user(telegram_id))

    # --- rate limiting ---
    async def incr_message_count(self, user_id: int, *, ttl: int) -> int:
        return await self._cache.incr_with_ttl(RedisKeys.rate_message(user_id), ttl=ttl)

    async def set_cooldown(self, user_id: int, *, ttl: int) -> None:
        await self._cache.set(RedisKeys.rate_cooldown(user_id), "1", ttl=ttl)

    async def is_on_cooldown(self, user_id: int) -> bool:
        return (await self._cache.get(RedisKeys.rate_cooldown(user_id))) is not None

    # --- job runtime context (progress message + lock token, key job:{id}) ---
    async def set_job_context(self, job_id: str, data: dict[str, Any], *, ttl: int) -> None:
        """Stash a job's request-side context for the worker (progress edits, 16.1)."""
        await self._cache.set(RedisKeys.job(job_id), _dumps(data), ttl=ttl)

    async def get_job_context(self, job_id: str) -> dict[str, Any] | None:
        raw = await self._cache.get(RedisKeys.job(job_id))
        return None if raw is None else _loads(raw)

    async def delete_job_context(self, job_id: str) -> None:
        await self._cache.delete(RedisKeys.job(job_id))

    # --- download lock ---
    async def acquire_download_lock(self, media_id: int, format_: str, quality: str) -> str | None:
        return await self._lock.acquire(
            RedisKeys.download_lock(media_id, format_, quality),
            ttl=self._settings.cache_lock_ttl,
        )

    async def release_download_lock(
        self, media_id: int, format_: str, quality: str, token: str
    ) -> bool:
        return await self._lock.release(RedisKeys.download_lock(media_id, format_, quality), token)


def _dumps(data: dict[str, Any]) -> str:
    return orjson.dumps(data).decode()


def _loads(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = orjson.loads(raw)
    return result
