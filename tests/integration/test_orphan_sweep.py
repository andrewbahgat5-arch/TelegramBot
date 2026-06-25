"""Integration tests for orphan sweeps (MASTER_PLAN Task 10.5).

``delete_orphaned`` removes ``active_downloads`` / ``job_waiters`` whose job has
reached a terminal state, while leaving rows for live (non-terminal) jobs intact.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.uuid7 import uuid7
from domain.enums import JobStatus
from infrastructure.database.models import MediaMetadata, User
from infrastructure.database.repositories import (
    ActiveDownloadRepository,
    JobRepository,
    JobWaiterRepository,
    MediaRepository,
    UserRepository,
)

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession, telegram_id: int) -> User:
    return await UserRepository(session).add(User(telegram_id=telegram_id))


async def _make_media(session: AsyncSession) -> MediaMetadata:
    return await MediaRepository(session).add(
        MediaMetadata(
            platform="youtube",
            video_id="orphan",
            title="Orphan",
            source_url="https://youtube.com/watch?v=orphan",
        )
    )


async def _create_job(
    session: AsyncSession, *, user_id: int, media_id: int, status: str
) -> uuid.UUID:
    job_id = uuid7()
    await JobRepository(session).create(
        job_id=job_id,
        user_id=user_id,
        media_id=media_id,
        format_="video",
        quality="720p",
        priority=1000,
        correlation_id=None,
        status=status,
    )
    return job_id


async def test_delete_orphaned_active_downloads(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    media = await _make_media(db_session)
    live = await _create_job(
        db_session, user_id=user.id, media_id=media.id, status=JobStatus.PROCESSING.value
    )
    terminal = await _create_job(
        db_session, user_id=user.id, media_id=media.id, status=JobStatus.COMPLETED.value
    )

    repo = ActiveDownloadRepository(db_session)
    await repo.insert_if_absent(media_id=media.id, format_="video", quality="720p", job_id=live)
    await repo.insert_if_absent(media_id=media.id, format_="video", quality="480p", job_id=terminal)

    removed = await repo.delete_orphaned()

    assert removed == 1  # only the completed job's slot
    assert await repo.get_by_media_format_quality(media.id, "video", "720p") is not None
    assert await repo.get_by_media_format_quality(media.id, "video", "480p") is None


async def test_delete_orphaned_job_waiters(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _make_user(db_session, telegram_id)
    media = await _make_media(db_session)
    live = await _create_job(
        db_session, user_id=user.id, media_id=media.id, status=JobStatus.QUEUED.value
    )
    terminal = await _create_job(
        db_session, user_id=user.id, media_id=media.id, status=JobStatus.CANCELLED.value
    )

    repo = JobWaiterRepository(db_session)
    await repo.add_waiter(job_id=live, user_id=user.id, correlation_id=None)
    await repo.add_waiter(job_id=terminal, user_id=user.id, correlation_id=None)

    removed = await repo.delete_orphaned()

    assert removed == 1
    assert len(await repo.list_for_job(live)) == 1
    assert len(await repo.list_for_job(terminal)) == 0
