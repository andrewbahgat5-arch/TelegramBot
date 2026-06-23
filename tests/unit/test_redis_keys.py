"""Unit tests pinning the LOCKED Redis key scheme (MASTER_PLAN 11.4)."""

from __future__ import annotations

from core.redis_keys import RedisKeys


def test_key_patterns_match_section_11_4() -> None:
    assert RedisKeys.file_id(42, "mp4", "720p") == "fileid:42:mp4:720p"
    assert RedisKeys.metadata("youtube", "dQw4w9WgXcQ") == "meta:youtube:dQw4w9WgXcQ"
    assert RedisKeys.user(123456789) == "user:123456789"
    assert RedisKeys.download_lock(42, "mp4", "720p") == "lock:42:mp4:720p"
    assert RedisKeys.rate_message(123456789) == "rate:msg:123456789"
    assert RedisKeys.rate_cooldown(123456789) == "rate:dl_cooldown:123456789"
    assert RedisKeys.setting("free_daily_limit") == "settings:free_daily_limit"
    assert RedisKeys.job("01J") == "job:01J"
    assert RedisKeys.worker_heartbeat("dl-1") == "worker:heartbeat:dl-1"


def test_fixed_keys() -> None:
    assert RedisKeys.QUEUE_JOBS == "queue:jobs"
    assert RedisKeys.QUEUE_ACTIVE == "queue:active"
