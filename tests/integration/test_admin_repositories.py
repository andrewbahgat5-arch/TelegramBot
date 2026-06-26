"""Integration tests for the Sprint 8 admin/broadcast SQL (MASTER_PLAN Task 8.1/8.2/8.3).

Exercises the live-DB queries the in-memory fakes cannot validate: the user
aggregate counts and the broadcast-audience filter/cursor (10.2), the broadcast
lifecycle UPDATEs (10.9), and the Task 8.3 admin reads — ``JobRepository.list_recent``
and ``ErrorLogRepository.list_recent`` (newest-first ordering + filters). Auto-skips
when Postgres is unavailable (see conftest).
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.uuid7 import uuid7
from infrastructure.database.models import ErrorLog, Job, MediaMetadata, User
from infrastructure.database.repositories import (
    BroadcastRepository,
    ErrorLogRepository,
    JobRepository,
    MediaRepository,
    UserRepository,
)

pytestmark = pytest.mark.asyncio


async def _user(session: AsyncSession, tid: int, **kw: object) -> User:
    return await UserRepository(session).add(User(telegram_id=tid, **kw))


async def test_user_stats_counts(db_session: AsyncSession, telegram_id: int) -> None:
    repo = UserRepository(db_session)
    base = await repo.count_all()
    banned_base = await repo.count_banned()
    downloads_base = await repo.sum_total_downloads()

    await _user(db_session, telegram_id, total_downloads=5)
    await _user(db_session, telegram_id + 1, total_downloads=3, is_banned=True)

    assert await repo.count_all() == base + 2
    assert await repo.count_banned() == banned_base + 1
    assert await repo.sum_total_downloads() == downloads_base + 8


async def test_broadcast_audience_filters_exclude_banned(
    db_session: AsyncSession, telegram_id: int
) -> None:
    # A unique language marker isolates this audience from real rows in the shared DB.
    lang = f"z{telegram_id % 100000000:08d}"
    repo = UserRepository(db_session)
    await _user(db_session, telegram_id, role="user", language=lang)
    await _user(db_session, telegram_id + 1, role="user", language=lang)
    await _user(db_session, telegram_id + 2, role="moderator", language=lang)
    await _user(db_session, telegram_id + 3, role="user", language=lang, is_banned=True)

    # Untargeted: excludes banned AND staff (moderator) → only the 2 normal users (#14).
    assert await repo.count_for_broadcast(role=None, language=lang) == 2
    # Explicit role targets exactly that role.
    assert await repo.count_for_broadcast(role="moderator", language=lang) == 1


async def test_broadcast_audience_pages_by_id_cursor(
    db_session: AsyncSession, telegram_id: int
) -> None:
    lang = (
        f"z{telegram_id % 100000000:08d}"  # unique marker → only this test's users are the audience
    )
    repo = UserRepository(db_session)
    a = await _user(db_session, telegram_id, language=lang)
    b = await _user(db_session, telegram_id + 1, language=lang)
    c = await _user(db_session, telegram_id + 2, language=lang)

    first = await repo.page_for_broadcast(after_id=0, limit=2, role=None, language=lang)
    assert [u.id for u in first] == [a.id, b.id]  # ascending id cursor
    second = await repo.page_for_broadcast(after_id=b.id, limit=2, role=None, language=lang)
    assert [u.id for u in second] == [c.id]


async def test_broadcast_lifecycle_and_counters(db_session: AsyncSession, telegram_id: int) -> None:
    user = await _user(db_session, telegram_id)
    repo = BroadcastRepository(db_session)
    created = await repo.create_pending(
        created_by=user.id,
        message_text="hi",
        target_language=None,
        target_role=None,
        expected_total=3,
    )
    assert created.status == "pending"

    nxt = await repo.get_next_pending()
    assert nxt is not None and nxt.id == created.id

    await repo.set_status(created.id, "in_progress")
    await repo.add_counts(created.id, sent=2, failed=1)
    await repo.add_counts(created.id, sent=1, failed=0)

    refreshed = await repo.get_by_id(created.id)
    assert refreshed is not None
    assert refreshed.total_sent == 3 and refreshed.total_failed == 1
    assert refreshed.status == "in_progress"


async def test_broadcast_due_poller_filters_scheduled(
    db_session: AsyncSession, telegram_id: int
) -> None:
    user = await _user(db_session, telegram_id)
    repo = BroadcastRepository(db_session)
    now = datetime.datetime.now(datetime.UTC)

    # Only a not-yet-due scheduled broadcast exists → the due-poller finds nothing.
    await repo.create_pending(
        created_by=user.id,
        message_text="later",
        target_language=None,
        target_role=None,
        expected_total=0,
        scheduled_at=now + datetime.timedelta(hours=1),
    )
    assert await repo.get_next_pending(now=now) is None

    # An immediate (NULL scheduled_at) broadcast is due now.
    immediate = await repo.create_pending(
        created_by=user.id,
        message_text="now",
        target_language=None,
        target_role=None,
        expected_total=0,
    )
    nxt = await repo.get_next_pending(now=now)
    assert nxt is not None and nxt.id == immediate.id

    # Once its scheduled time passes, the scheduled one becomes due too.
    later = now + datetime.timedelta(hours=2)
    assert await repo.get_next_pending(now=later) is not None


async def test_job_list_recent_orders_newest_first_and_filters_status(
    db_session: AsyncSession, telegram_id: int
) -> None:
    user = await _user(db_session, telegram_id)
    media = await MediaRepository(db_session).add(
        MediaMetadata(
            platform="youtube",
            video_id=f"j{telegram_id}",
            title="t",
            source_url="https://youtube.com/watch?v=x",
        )
    )
    repo = JobRepository(db_session)
    # Postgres now() is transaction-constant, so set created_at explicitly to order.
    now = datetime.datetime.now(datetime.UTC)
    older = await repo.add(
        Job(
            id=uuid7(),
            user_id=user.id,
            media_id=media.id,
            format="video",
            quality="480p",
            status="completed",
            created_at=now - datetime.timedelta(seconds=5),
        )
    )
    newer = await repo.add(
        Job(
            id=uuid7(),
            user_id=user.id,
            media_id=media.id,
            format="video",
            quality="720p",
            status="failed",
            error_message="boom",
            created_at=now,
        )
    )

    recent = await repo.list_recent(limit=10)
    ids = [str(job.id) for job in recent]
    # Newest-first: this user's newer job precedes its older job.
    assert ids.index(str(newer.id)) < ids.index(str(older.id))

    failed = await repo.list_recent(limit=50, status="failed")
    assert str(newer.id) in [str(j.id) for j in failed]
    assert str(older.id) not in [str(j.id) for j in failed]


async def test_error_log_list_recent_orders_and_filters_type(
    db_session: AsyncSession, telegram_id: int
) -> None:
    repo = ErrorLogRepository(db_session)
    marker = f"itest_{telegram_id}"
    now = datetime.datetime.now(datetime.UTC)
    older = await repo.add(
        ErrorLog(
            error_type="download_failed",
            message=marker,
            created_at=now - datetime.timedelta(seconds=5),
        )
    )
    newer = await repo.add(
        ErrorLog(
            error_type="provider_error",
            message=marker,
            created_at=now,
        )
    )

    recent = await repo.list_recent(limit=50)
    ours = [e.id for e in recent if e.message == marker]
    assert ours.index(newer.id) < ours.index(older.id)  # newest first

    provider = await repo.list_recent(limit=50, error_type="provider_error")
    provider_ids = [e.id for e in provider]
    assert newer.id in provider_ids and older.id not in provider_ids
