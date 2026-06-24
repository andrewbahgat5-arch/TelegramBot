"""Unit tests for JobService's decision tree (MASTER_PLAN Task 6.4, flows 16.1-16.2)."""

from __future__ import annotations

import datetime
from typing import Any

from core.uuid7 import uuid7
from domain.entities.media import MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import CachedFileExpiredError
from services.job_service import JobService, RequestKind, RequestOutcome
from services.notification_service import NotificationService
from services.queue_service import QueueService
from tests.unit._fakes import (
    FakeActiveDownloadRepo,
    FakeCachedFileRepo,
    FakeDownloadRepo,
    FakeFileSender,
    FakeJobRepo,
    FakeJobRow,
    FakeJobWaiterRepo,
    FakeMessageSender,
    FakeQueueBackend,
    FakeUser,
    FakeUserRepo,
    load_settings,
    make_cache_service,
)

_INFO = MediaInfo(platform="youtube", video_id="vid", title="Clip", source_url="https://x/clip")


def _build(*, sender: FakeFileSender | None = None) -> dict[str, Any]:
    cache_service, _ = make_cache_service()
    backend = FakeQueueBackend()
    jobs = FakeJobRepo()
    cached = FakeCachedFileRepo()
    active = FakeActiveDownloadRepo()
    waiters = FakeJobWaiterRepo()
    downloads = FakeDownloadRepo()
    users = FakeUserRepo()
    sender = sender or FakeFileSender()
    msg = FakeMessageSender()
    service = JobService(
        job_repo=jobs,
        cached_file_repo=cached,
        active_download_repo=active,
        job_waiter_repo=waiters,
        download_repo=downloads,
        user_repo=users,
        queue_service=QueueService(backend),
        cache_service=cache_service,
        file_sender=sender,
        notification_service=NotificationService(msg),
        settings=load_settings(),
    )
    return {
        "service": service,
        "backend": backend,
        "jobs": jobs,
        "cached": cached,
        "active": active,
        "waiters": waiters,
        "downloads": downloads,
        "users": users,
        "sender": sender,
        "msg": msg,
    }


async def _request(service: JobService) -> RequestOutcome:
    return await service.request(
        user_id=7,
        telegram_id=555,
        media_id=42,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=999,
    )


async def test_cache_miss_creates_job_waiter_and_enqueues() -> None:
    env = _build()
    service: JobService = env["service"]

    outcome = await _request(service)

    assert outcome.kind is RequestKind.QUEUED
    assert await env["backend"].depth() == 1
    assert len(env["jobs"].jobs) == 1
    assert len(env["waiters"].waiters) == 1
    assert (42, "video", "720p") in env["active"].by_key
    # Worker context carries the progress message + lock token.
    assert outcome.job_id is not None
    ctx = await service._cache.get_job_context(outcome.job_id)
    assert ctx is not None and ctx["message_id"] == 999 and ctx["lock_token"]
    # The originator is the first per-waiter progress entry (used for fan-out ✅/❌).
    assert ctx["progress"]["7"] == {"telegram_id": 555, "message_id": 999}


async def test_cache_hit_delivers_instantly_without_a_job() -> None:
    env = _build()
    service: JobService = env["service"]
    users: FakeUserRepo = env["users"]
    users.by_tid[555] = FakeUser(id=7, telegram_id=555)
    await env["cached"].upsert(
        media_id=42,
        format_="video",
        quality="720p",
        telegram_file_id="cached-fid",
        telegram_unique_file_id="u",
        file_size=123,
    )

    outcome = await _request(service)

    assert outcome.kind is RequestKind.CACHED
    assert await env["backend"].depth() == 0  # no job queued
    assert env["sender"].sent == [(555, "cached-fid")]
    assert len(env["downloads"].rows) == 1
    assert users.by_tid[555].total_downloads == 1


async def test_cache_hit_with_invalid_file_id_evicts_and_redownloads() -> None:
    # A cached file_id minted by a different bot/API server is rejected by Telegram.
    sender = FakeFileSender(send_cached_error=CachedFileExpiredError("wrong file identifier"))
    env = _build(sender=sender)
    service: JobService = env["service"]
    users: FakeUserRepo = env["users"]
    users.by_tid[555] = FakeUser(id=7, telegram_id=555)
    cached: FakeCachedFileRepo = env["cached"]
    await cached.upsert(
        media_id=42,
        format_="video",
        quality="720p",
        telegram_file_id="stale-fid",
        telegram_unique_file_id="u",
        file_size=123,
    )

    outcome = await _request(service)

    # Falls through to a fresh download instead of failing the user.
    assert outcome.kind is RequestKind.QUEUED
    assert await env["backend"].depth() == 1
    # The stale cache entry was evicted (DB + Redis fast path).
    assert await cached.get_by_media_format_quality(42, "video", "720p") is None
    assert await service._cache.get_file_id(42, "video", "720p") is None
    assert len(env["downloads"].rows) == 0  # nothing recorded for the failed resend


async def test_single_active_blocks_free_users_second_download() -> None:
    env = _build()
    service: JobService = env["service"]

    first = await service.request(
        user_id=7,
        telegram_id=555,
        media_id=42,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=999,
        single_active=True,
    )
    assert first.kind is RequestKind.QUEUED

    # A different media while the first job is still in flight → rejected (free cap).
    second = await service.request(
        user_id=7,
        telegram_id=555,
        media_id=99,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=1000,
        single_active=True,
    )
    assert second.kind is RequestKind.BUSY
    assert await env["backend"].depth() == 1  # the second job was never queued
    assert len(env["jobs"].jobs) == 1
    # The lock for the second media was released (not left dangling).
    assert await service._cache.acquire_download_lock(99, "video", "720p") is not None


async def test_single_active_ignores_stale_stuck_job() -> None:
    # A non-terminal job orphaned long ago (worker died before the Sprint-10 reaper
    # exists) must NOT block forever — it ages out of the active window (#24).
    env = _build()
    service: JobService = env["service"]
    stuck = FakeJobRow(
        id=uuid7(),
        user_id=7,
        media_id=1,
        format="video",
        quality="720p",
        status="processing",
        created_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1),
    )
    env["jobs"].jobs[stuck.id] = stuck

    outcome = await service.request(
        user_id=7,
        telegram_id=555,
        media_id=42,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=1,
        single_active=True,
    )
    assert outcome.kind is RequestKind.QUEUED  # the stale job did not block the new one


async def test_single_active_off_allows_concurrent_downloads() -> None:
    env = _build()
    service: JobService = env["service"]

    await service.request(
        user_id=7,
        telegram_id=555,
        media_id=42,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=1,
        single_active=False,
    )
    second = await service.request(
        user_id=7,
        telegram_id=555,
        media_id=99,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=2,
        single_active=False,
    )
    assert second.kind is RequestKind.QUEUED
    assert await env["backend"].depth() == 2  # premium-style: both queued


async def test_duplicate_active_request_attaches_waiter() -> None:
    env = _build()
    service: JobService = env["service"]
    # First request claims the active slot.
    first = await _request(service)
    # Second request for the same (media, format, quality) by another user.
    second = await service.request(
        user_id=8,
        telegram_id=556,
        media_id=42,
        info=_INFO,
        format_=MediaFormat.VIDEO,
        quality=Quality.P720,
        progress_message_id=1000,
    )

    assert second.kind is RequestKind.DUPLICATE
    assert second.job_id == first.job_id
    # Both the originator and the duplicate are waiters on the one job.
    assert len(env["waiters"].waiters) == 2
    assert await env["backend"].depth() == 1  # still one job
    # The duplicate's progress message is registered so the worker notifies them too.
    assert first.job_id is not None
    ctx = await service._cache.get_job_context(first.job_id)
    assert ctx is not None
    assert ctx["progress"]["7"] == {"telegram_id": 555, "message_id": 999}  # originator
    assert ctx["progress"]["8"] == {"telegram_id": 556, "message_id": 1000}  # duplicate
