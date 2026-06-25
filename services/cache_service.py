"""CacheService (MASTER_PLAN Component 9.2, Task 3.5).

The single, audited entry point for Redis cache + download-lock operations. Exposes
typed methods only — callers never pass raw key strings (exit criterion). Keys come
from ``core.redis_keys.RedisKeys``; dict values are serialized with orjson.
"""

from __future__ import annotations

from typing import Any

import orjson

from core import metrics
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
        value = await self._cache.get(RedisKeys.file_id(media_id, format_, quality))
        metrics.record_cache("fileid", hit=value is not None)
        return value

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
        metrics.record_cache("metadata", hit=raw is not None)
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
        metrics.record_cache("user", hit=raw is not None)
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

    async def add_waiter_progress(
        self, job_id: str, user_id: int, telegram_id: int, message_id: int
    ) -> None:
        """Register a fan-out waiter's progress message so the worker can notify them.

        Best-effort: progress display is cosmetic (delivery correctness comes from the
        durable ``job_waiters`` table). A lost update under a rare concurrent attach
        only means that waiter sees no ✅/❌ edit, not a missed file.
        """
        ctx = await self.get_job_context(job_id) or {}
        progress = dict(ctx.get("progress", {}))
        progress[str(user_id)] = {"telegram_id": telegram_id, "message_id": message_id}
        ctx["progress"] = progress
        await self.set_job_context(job_id, ctx, ttl=self._settings.cache_lock_ttl)

    async def record_uploaded_file(self, job_id: str, file_id: str, unique_file_id: str) -> None:
        """Persist the minted ``file_id`` so a retried worker reuses it (idempotency).

        Survives the per-job DB transaction's rollback (Redis is outside it), so a
        retry after partial delivery skips the re-upload — the first waiter is never
        delivered to twice.
        """
        ctx = await self.get_job_context(job_id) or {}
        ctx["file_id"] = file_id
        ctx["unique_file_id"] = unique_file_id
        await self.set_job_context(job_id, ctx, ttl=self._settings.cache_lock_ttl)

    async def record_delivered(self, job_id: str, user_id: int) -> None:
        """Mark a waiter as already delivered so a retry won't re-send their file."""
        ctx = await self.get_job_context(job_id) or {}
        delivered = list(ctx.get("delivered", []))
        if user_id not in delivered:
            delivered.append(user_id)
        ctx["delivered"] = delivered
        await self.set_job_context(job_id, ctx, ttl=self._settings.cache_lock_ttl)

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
