"""Redis key scheme (MASTER_PLAN 11.4, LOCKED).

Every key pattern in Section 11.4 is emitted by exactly one helper here. This lives
in ``core`` because it is a cross-cutting helper used by several services
(``CacheService``, ``QueueService``, ``RateLimitService``) and the Redis adapters —
the file-placement rule for 3+-layer helpers (Section 7.1). Callers must never build
Redis keys by hand; use these methods so the scheme stays in one place.

Changing any pattern here is a change to the LOCKED key scheme and requires a
Section 14/decision-log update.
"""

from __future__ import annotations

from typing import Final


class RedisKeys:
    # Fixed keys (not parameterized).
    QUEUE_JOBS: Final[str] = "queue:jobs"
    QUEUE_ACTIVE: Final[str] = "queue:active"

    @staticmethod
    def file_id(media_id: int, format_: str, quality: str) -> str:
        return f"fileid:{media_id}:{format_}:{quality}"

    # Schema version of the cached metadata payload (the dict shape in
    # services/url_analyzer._to_cache). BUMP THIS whenever that shape changes — a new
    # field, a renamed key, a different structure. The version is part of the cache key,
    # so bumping it orphans every old entry (they expire via TTL) and readers only ever
    # see payloads written by the current code. Without this, adding a field left old
    # cached entries missing it, which silently served stale data to any user whose
    # request was cached before the deploy — a real bug (playlist item_url/has_audio,
    # 2026-07-21) that "worked in a fresh test but broke for a returning user".
    METADATA_SCHEMA_VERSION: Final[int] = 2

    @staticmethod
    def metadata(platform: str, video_id: str) -> str:
        return f"meta:v{RedisKeys.METADATA_SCHEMA_VERSION}:{platform}:{video_id}"

    @staticmethod
    def user(telegram_id: int) -> str:
        return f"user:{telegram_id}"

    @staticmethod
    def download_lock(media_id: int, format_: str, quality: str) -> str:
        return f"lock:{media_id}:{format_}:{quality}"

    @staticmethod
    def rate_message(user_id: int) -> str:
        return f"rate:msg:{user_id}"

    @staticmethod
    def rate_cooldown(user_id: int) -> str:
        return f"rate:dl_cooldown:{user_id}"

    @staticmethod
    def setting(key: str) -> str:
        return f"settings:{key}"

    @staticmethod
    def job(job_id: str) -> str:
        return f"job:{job_id}"

    @staticmethod
    def worker_heartbeat(worker_id: str) -> str:
        return f"worker:heartbeat:{worker_id}"

    @staticmethod
    def provider_health(name: str) -> str:
        # Provider health record (MASTER_PLAN 12.6.4). No TTL; overwritten by
        # health updates. Persisted form of the in-memory mirror (D-028).
        return f"provider:health:{name}"
