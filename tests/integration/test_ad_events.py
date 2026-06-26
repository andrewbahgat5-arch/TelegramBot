"""Integration tests for ``ad_events`` (MASTER_PLAN Task 9.5.9, D-045/D-052).

Exercises the live partitioned-table write + aggregate read that the in-memory fakes
cannot validate: an INSERT routes into the current-month partition, and
``count_for_ad`` aggregates by ad and event type. Auto-skips when Postgres is
unavailable (see conftest).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.repositories import AdEventRepository

pytestmark = pytest.mark.asyncio


async def test_record_and_count_by_type(db_session: AsyncSession, telegram_id: int) -> None:
    repo = AdEventRepository(db_session)
    ad_id = telegram_id  # unique per run → isolates this test's rows in the shared DB

    await repo.record(
        event_type="impression", advertisement_id=ad_id, user_id=1, placement="post_download"
    )
    await repo.record(event_type="click", advertisement_id=ad_id, user_id=1, button_id=5)
    await repo.record(event_type="impression", advertisement_id=ad_id, user_id=2, placement="home")

    assert await repo.count_for_ad(ad_id) == 3
    assert await repo.count_for_ad(ad_id, event_type="impression") == 2
    assert await repo.count_for_ad(ad_id, event_type="click") == 1


async def test_event_row_fields_persist(db_session: AsyncSession, telegram_id: int) -> None:
    repo = AdEventRepository(db_session)
    ad_id = telegram_id + 1

    event = await repo.record(event_type="click", advertisement_id=ad_id, user_id=99, button_id=7)

    assert event.id is not None  # identity assigned by the partition parent
    assert event.created_at is not None  # server default routed it into a live partition
    assert event.advertisement_id == ad_id
    assert event.event_type == "click"
    assert event.button_id == 7
