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

    @staticmethod
    def metadata(platform: str, video_id: str) -> str:
        return f"meta:{platform}:{video_id}"

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
