"""Unit tests for HistoryService (MASTER_PLAN Task 7.3, flow 16.3)."""

from __future__ import annotations

from typing import Any

from domain.entities.media import MediaInfo
from domain.exceptions import CachedFileExpiredError
from services.history_service import HistoryService, ResendKind
from services.job_service import JobService
from services.notification_service import NotificationService
from services.queue_service import QueueService
from services.settings_service import SettingsService
from services.url_analyzer import URLAnalyzerService
from tests.unit._fakes import (
    FakeActiveDownloadRepo,
    FakeCache,
    FakeCachedFileRepo,
    FakeDownloadRepo,
    FakeFileSender,
    FakeJobRepo,
    FakeJobWaiterRepo,
    FakeMediaRepo,
    FakeMessageSender,
    FakeProvider,
    FakeQueueBackend,
    FakeSettingsStore,
    FakeUserRepo,
    load_settings,
    make_cache_service,
)

_INFO = MediaInfo(platform="youtube", video_id="vid", title="Clip", source_url="https://x/clip")

# Page size the harness seeds into settings; kept small so a couple of rows span two pages.
_PAGE_SIZE = 5


def _build(
    *, sender: FakeFileSender | None = None, page_size: int | None = _PAGE_SIZE
) -> dict[str, Any]:
    cache_service, _ = make_cache_service()
    media_repo = FakeMediaRepo()
    cached = FakeCachedFileRepo()
    downloads = FakeDownloadRepo()
    backend = FakeQueueBackend()
    sender = sender or FakeFileSender()
    analyzer = URLAnalyzerService(FakeProvider("p", result=_INFO), cache_service, media_repo)
    # ``page_size=None`` leaves the key unseeded so the service falls back to its default.
    data = {"history_page_size": (str(page_size), "int")} if page_size is not None else {}
    settings_service = SettingsService(FakeSettingsStore(data), FakeCache())
    job_service = JobService(
        job_repo=FakeJobRepo(),
        cached_file_repo=cached,
        active_download_repo=FakeActiveDownloadRepo(),
        job_waiter_repo=FakeJobWaiterRepo(),
        download_repo=downloads,
        user_repo=FakeUserRepo(),
        queue_service=QueueService(backend),
        cache_service=cache_service,
        file_sender=sender,
        notification_service=NotificationService(FakeMessageSender()),
        settings=load_settings(),
    )
    service = HistoryService(
        download_repo=downloads,
        cached_file_repo=cached,
        job_service=job_service,
        analyzer=analyzer,
        file_sender=sender,
        cache_service=cache_service,
        settings_service=settings_service,
    )
    return {
        "service": service,
        "downloads": downloads,
        "cached": cached,
        "media_repo": media_repo,
        "backend": backend,
        "sender": sender,
        "cache_service": cache_service,
        "settings": settings_service,
    }


async def _seed_media(env: dict[str, Any]) -> int:
    row = await env["media_repo"].upsert_metadata(
        platform="youtube", video_id="vid", title="Clip", source_url=_INFO.source_url
    )
    media_id: int = row.id
    return media_id


async def _seed_cached_download(
    env: dict[str, Any], *, user_id: int = 7, file_id: str = "fid"
) -> int:
    media_id = await _seed_media(env)
    cached = await env["cached"].upsert(
        media_id=media_id,
        format_="video",
        quality="720p",
        telegram_file_id=file_id,
        telegram_unique_file_id="u",
        file_size=123,
    )
    row = await env["downloads"].create_completed(
        user_id=user_id,
        cached_file_id=cached.id,
        platform="youtube",
        format_="video",
        quality="720p",
        file_size=123,
    )
    return int(row.id)


async def _seed_history_rows(env: dict[str, Any], count: int, *, user_id: int = 7) -> None:
    for _ in range(count):
        await env["downloads"].create_completed(
            user_id=user_id,
            cached_file_id=None,
            platform="youtube",
            format_="video",
            quality="720p",
            file_size=1,
        )


async def test_list_history_paginates_newest_first() -> None:
    env = _build()
    await _seed_history_rows(env, _PAGE_SIZE + 2)  # 7 rows

    first = await env["service"].list_history(7, page=0)
    assert len(first.rows) == _PAGE_SIZE
    assert first.has_next is True and first.has_prev is False
    # Newest first: the highest id comes first.
    assert first.rows[0].id > first.rows[-1].id

    second = await env["service"].list_history(7, page=1)
    assert len(second.rows) == 2
    assert second.has_next is False and second.has_prev is True


async def test_list_history_honours_configured_page_size() -> None:
    # Operator tuned the §13.4 ``history_page_size`` key down to 2.
    env = _build(page_size=2)
    await _seed_history_rows(env, 3)

    first = await env["service"].list_history(7, page=0)
    assert len(first.rows) == 2
    assert first.has_next is True


async def test_list_history_falls_back_to_default_when_unseeded() -> None:
    # Key missing → SettingNotFoundError → default of 7, so 6 rows fit on one page.
    env = _build(page_size=None)
    await _seed_history_rows(env, 6)

    first = await env["service"].list_history(7, page=0)
    assert len(first.rows) == 6
    assert first.has_next is False


async def test_resend_from_cache_delivers_without_new_history_row() -> None:
    env = _build()
    download_id = await _seed_cached_download(env)

    outcome = await env["service"].resend(
        download_id=download_id, user_id=7, telegram_id=555, progress_message_id=900
    )

    assert outcome is ResendKind.RESENT
    assert env["sender"].sent == [(555, "fid")]
    # Resend bumps usage but never inserts a duplicate history row (16.3 step 5).
    assert env["cached"].by_id[1].usage_count == 2  # 1 at upsert + 1 on resend
    assert len(env["downloads"].rows) == 1


async def test_resend_invalid_file_id_falls_back_to_fresh_download() -> None:
    sender = FakeFileSender(send_cached_error=CachedFileExpiredError("wrong file identifier"))
    env = _build(sender=sender)
    download_id = await _seed_cached_download(env, file_id="stale")

    outcome = await env["service"].resend(
        download_id=download_id, user_id=7, telegram_id=555, progress_message_id=900
    )

    assert outcome is ResendKind.REQUEUED
    # Stale cache evicted and a fresh job queued (16.3 step 4).
    assert await env["cached"].get_by_media_format_quality(1, "video", "720p") is None
    assert await env["backend"].depth() == 1


async def test_resend_null_cached_file_needs_relink() -> None:
    env = _build()
    row = await env["downloads"].create_completed(
        user_id=7,
        cached_file_id=None,  # FK SET NULL: no media to reconstruct from
        platform="youtube",
        format_="video",
        quality="720p",
        file_size=1,
    )

    outcome = await env["service"].resend(
        download_id=int(row.id), user_id=7, telegram_id=555, progress_message_id=900
    )

    assert outcome is ResendKind.NEEDS_RELINK
    assert env["sender"].sent == []


async def test_resend_other_users_download_is_not_found() -> None:
    env = _build()
    download_id = await _seed_cached_download(env, user_id=7)

    outcome = await env["service"].resend(
        download_id=download_id, user_id=999, telegram_id=999, progress_message_id=900
    )

    assert outcome is ResendKind.NOT_FOUND
    assert env["sender"].sent == []
