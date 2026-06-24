"""Integration tests for the Sprint 8 admin/broadcast SQL (MASTER_PLAN Task 8.1/8.2).

Exercises the live-DB queries the in-memory fakes cannot validate: the user
aggregate counts and the broadcast-audience filter/cursor (10.2), and the broadcast
lifecycle UPDATEs (10.9). Auto-skips when Postgres is unavailable (see conftest).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import User
from infrastructure.database.repositories import BroadcastRepository, UserRepository

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

    # Banned users are never in the audience; role narrows it further.
    assert await repo.count_for_broadcast(role=None, language=lang) == 3
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
