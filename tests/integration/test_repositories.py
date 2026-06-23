"""Repository CRUD + behavior tests (MASTER_PLAN Task 2.7, 2.9)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.uuid7 import uuid7
from infrastructure.database.models import (
    ActiveDownload,
    Broadcast,
    CachedFile,
    Download,
    Job,
    JobWaiter,
    MediaMetadata,
    User,
    UserPreference,
)
from infrastructure.database.repositories import (
    ActiveDownloadRepository,
    BroadcastRepository,
    CachedFileRepository,
    DownloadRepository,
    JobRepository,
    JobWaiterRepository,
    MediaRepository,
    SettingsRepository,
    UserPreferenceRepository,
    UserRepository,
)

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession, telegram_id: int) -> User:
    return await UserRepository(session).add(User(telegram_id=telegram_id))


async def _make_media(session: AsyncSession, video_id: str = "abc123") -> MediaMetadata:
    return await MediaRepository(session).add(
        MediaMetadata(
            platform="youtube",
            video_id=video_id,
            title="Test",
            source_url="https://youtube.com/watch?v=abc123",
        )
    )


async def test_user_crud_and_lookup(db_session: AsyncSession, telegram_id: int) -> None:
    repo = UserRepository(db_session)
    user = await repo.add(User(telegram_id=telegram_id))
    assert user.id is not None
    assert (await repo.get_by_id(user.id)) is not None
    fetched = await repo.get_by_telegram_id(telegram_id)
    assert fetched is not None
    assert fetched.role == "user"


async def test_user_lazy_daily_reset(db_session: AsyncSession, telegram_id: int) -> None:
    repo = UserRepository(db_session)
    yesterday = datetime.date(2026, 1, 1)
    user = await repo.add(
        User(
            telegram_id=telegram_id,
            daily_download_count=7,
            daily_download_count_reset_date=yesterday,
        )
    )
    today = datetime.date(2026, 1, 2)
    refreshed = await repo.reset_daily_download_count_if_needed(user, today=today)
    assert refreshed.daily_download_count == 0
    assert refreshed.daily_download_count_reset_date == today


async def test_user_daily_reset_noop_same_day(db_session: AsyncSession, telegram_id: int) -> None:
    repo = UserRepository(db_session)
    today = datetime.date(2026, 1, 2)
    user = await repo.add(
        User(
            telegram_id=telegram_id,
            daily_download_count=4,
            daily_download_count_reset_date=today,
        )
    )
    refreshed = await repo.reset_daily_download_count_if_needed(user, today=today)
    assert refreshed.daily_download_count == 4


async def test_media_get_by_platform_video(db_session: AsyncSession) -> None:
    repo = MediaRepository(db_session)
    await repo.add(
        MediaMetadata(
            platform="tiktok",
            video_id="xyz",
            title="T",
            source_url="https://tiktok.com/xyz",
        )
    )
    found = await repo.get_by_platform_video("tiktok", "xyz")
    assert found is not None
    assert (await repo.get_by_platform_video("tiktok", "missing")) is None


async def test_cached_file_lookup(db_session: AsyncSession) -> None:
    media = await _make_media(db_session)
    repo = CachedFileRepository(db_session)
    await repo.add(
        CachedFile(
            media_id=media.id,
            format="video",
            quality="720p",
            telegram_file_id="fid",
            telegram_unique_file_id="ufid",
            file_size=1024,
        )
    )
    found = await repo.get_by_media_format_quality(media.id, "video", "720p")
    assert found is not None
    assert found.telegram_file_id == "fid"


async def test_job_create_accepts_uuid7(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    media = await _make_media(db_session)
    repo = JobRepository(db_session)
    job_id = uuid7()
    await repo.add(
        Job(
            id=job_id,
            user_id=user.id,
            media_id=media.id,
            format="video",
            quality="720p",
        )
    )
    fetched = await repo.get_by_uuid(job_id)
    assert fetched is not None
    assert fetched.status == "created"
    assert fetched.priority == 1000


async def test_active_download_unique_constraint(
    db_session: AsyncSession, telegram_id: int
) -> None:
    media = await _make_media(db_session)
    repo = ActiveDownloadRepository(db_session)
    await repo.add(
        ActiveDownload(media_id=media.id, format="video", quality="720p", job_id=uuid7())
    )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await repo.add(
                ActiveDownload(media_id=media.id, format="video", quality="720p", job_id=uuid7())
            )
    found = await repo.get_by_media_format_quality(media.id, "video", "720p")
    assert found is not None


async def test_job_waiter_list_and_delete(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    repo = JobWaiterRepository(db_session)
    job_id = uuid7()
    await repo.add(JobWaiter(job_id=job_id, user_id=user.id))
    waiters = await repo.list_for_job(job_id)
    assert len(waiters) == 1
    removed = await repo.delete_for_job(job_id)
    assert removed == 1
    assert await repo.list_for_job(job_id) == []


async def test_settings_get_and_upsert(db_session: AsyncSession) -> None:
    repo = SettingsRepository(db_session)
    existing = await repo.get_by_key("free_daily_limit")
    assert existing is not None
    assert existing.value == "10"
    updated = await repo.upsert("free_daily_limit", "25")
    assert updated.value == "25"
    assert (await repo.get_by_key("free_daily_limit")).value == "25"  # type: ignore[union-attr]


async def test_download_list_for_user_pagination(
    db_session: AsyncSession, telegram_id: int
) -> None:
    user = await _make_user(db_session, telegram_id)
    repo = DownloadRepository(db_session)
    # Use timestamps inside the seeded partition window (current month onward).
    base = datetime.datetime.now(datetime.UTC).replace(microsecond=0)
    for i in range(3):
        await repo.add(
            Download(
                user_id=user.id,
                platform="youtube",
                format="video",
                quality="720p",
                status="completed",
                created_at=base - datetime.timedelta(minutes=i * 5),
            )
        )
    newest = await repo.list_for_user(user.id, limit=2)
    assert len(newest) == 2
    # Newest first (base is the most recent).
    assert newest[0].created_at > newest[1].created_at
    assert newest[0].created_at == base


async def test_generic_list_paginated_and_delete(
    db_session: AsyncSession, telegram_id: int
) -> None:
    user = await _make_user(db_session, telegram_id)
    repo = BroadcastRepository(db_session)
    created = await repo.add(Broadcast(created_by=user.id, message_text="hello", expected_total=5))
    listed = await repo.list_paginated(limit=10)
    assert any(b.id == created.id for b in listed)
    await repo.delete(created)
    assert (await repo.get_by_id(created.id)) is None


async def test_user_preference_get_by_user_id(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    repo = UserPreferenceRepository(db_session)
    await repo.add(UserPreference(user_id=user.id, notifications_enabled=False))
    found = await repo.get_by_user_id(user.id)
    assert found is not None
    assert found.notifications_enabled is False
    assert (await repo.get_by_user_id(user.id + 1)) is None
