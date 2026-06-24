"""Integration tests for the Sprint 6 repository methods (MASTER_PLAN Task 6.4/6.5).

These exercise the PostgreSQL-specific SQL the pipeline relies on — ``INSERT … ON
CONFLICT … RETURNING`` (cache UPSERT, active-slot claim, waiter add) and the lazy
counter ``CASE`` — against a live database, which the in-memory unit fakes cannot
validate. The suite auto-skips when Postgres is unavailable (see conftest).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.uuid7 import uuid7
from domain.enums import JobStatus
from infrastructure.database.models import MediaMetadata, User
from infrastructure.database.repositories import (
    ActiveDownloadRepository,
    CachedFileRepository,
    DownloadRepository,
    JobRepository,
    JobWaiterRepository,
    MediaRepository,
    UserRepository,
)

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession, telegram_id: int) -> User:
    return await UserRepository(session).add(User(telegram_id=telegram_id))


async def _make_media(session: AsyncSession, video_id: str = "s6vid") -> MediaMetadata:
    return await MediaRepository(session).add(
        MediaMetadata(
            platform="youtube",
            video_id=video_id,
            title="Test",
            source_url="https://youtube.com/watch?v=s6vid",
        )
    )


async def test_cached_file_upsert_inserts_then_updates(db_session: AsyncSession) -> None:
    media = await _make_media(db_session)
    repo = CachedFileRepository(db_session)

    first = await repo.upsert(
        media_id=media.id,
        format_="video",
        quality="720p",
        telegram_file_id="fid-1",
        telegram_unique_file_id="u-1",
        file_size=100,
    )
    assert first.usage_count == 1

    second = await repo.upsert(
        media_id=media.id,
        format_="video",
        quality="720p",
        telegram_file_id="fid-2",
        telegram_unique_file_id="u-2",
        file_size=200,
    )
    assert second.id == first.id  # same row (unique key)
    assert second.telegram_file_id == "fid-2"
    assert second.usage_count == 2  # bumped on conflict

    await repo.bump_usage(second.id)
    refetched = await repo.get_by_media_format_quality(media.id, "video", "720p")
    assert refetched is not None and refetched.usage_count == 3


async def test_active_download_claim_is_exclusive(db_session: AsyncSession) -> None:
    media = await _make_media(db_session)
    repo = ActiveDownloadRepository(db_session)
    job_a, job_b = uuid7(), uuid7()

    assert await repo.insert_if_absent(
        media_id=media.id, format_="video", quality="720p", job_id=job_a
    )
    # A second claim for the same (media, format, quality) is rejected.
    assert not await repo.insert_if_absent(
        media_id=media.id, format_="video", quality="720p", job_id=job_b
    )
    existing = await repo.get_by_media_format_quality(media.id, "video", "720p")
    assert existing is not None and existing.job_id == job_a

    assert await repo.delete_by_job(job_a) == 1
    # Slot is free again after the job is cleared.
    assert await repo.insert_if_absent(
        media_id=media.id, format_="video", quality="720p", job_id=job_b
    )


async def test_job_waiter_add_is_idempotent(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    repo = JobWaiterRepository(db_session)
    job_id = uuid7()

    assert await repo.add_waiter(job_id=job_id, user_id=user.id, correlation_id=None)
    assert not await repo.add_waiter(job_id=job_id, user_id=user.id, correlation_id=None)
    assert len(await repo.list_for_job(job_id)) == 1
    assert await repo.delete_for_job(job_id) == 1


async def test_job_create_and_state_transitions(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    media = await _make_media(db_session)
    repo = JobRepository(db_session)
    job_id = uuid7()

    await repo.create(
        job_id=job_id,
        user_id=user.id,
        media_id=media.id,
        format_="video",
        quality="720p",
        priority=1000,
        correlation_id=None,
        status=JobStatus.QUEUED.value,
    )
    await repo.set_status(
        job_id, JobStatus.PROCESSING.value, started_at=datetime.datetime.now(datetime.UTC)
    )
    await repo.set_status(job_id, JobStatus.FAILED.value, increment_retry=True)
    await repo.set_status(
        job_id, JobStatus.COMPLETED.value, finished_at=datetime.datetime.now(datetime.UTC)
    )

    job = await repo.get_by_uuid(job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value
    assert job.retry_count == 1
    assert job.started_at is not None and job.finished_at is not None


async def test_increment_download_counters_lazy_reset(
    db_session: AsyncSession, telegram_id: int
) -> None:
    repo = UserRepository(db_session)
    user = await repo.add(
        User(
            telegram_id=telegram_id,
            daily_download_count=4,
            daily_download_count_reset_date=datetime.date(2026, 1, 1),
            total_downloads=10,
        )
    )

    await repo.increment_download_counters(user.id, today=datetime.date(2026, 6, 24))

    refreshed = await repo.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.total_downloads == 11
    assert refreshed.daily_download_count == 1  # stale date → reset to 1
    assert refreshed.daily_download_count_reset_date == datetime.date(2026, 6, 24)


async def test_download_create_completed(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    media = await _make_media(db_session)
    cached = await CachedFileRepository(db_session).upsert(
        media_id=media.id,
        format_="video",
        quality="720p",
        telegram_file_id="fid",
        telegram_unique_file_id="u",
        file_size=123,
    )
    repo = DownloadRepository(db_session)

    row = await repo.create_completed(
        user_id=user.id,
        cached_file_id=cached.id,
        platform="youtube",
        format_="video",
        quality="720p",
        file_size=123,
    )
    assert row.status == "completed"
    history = await repo.list_for_user(user.id)
    assert len(history) == 1 and history[0].cached_file_id == cached.id
