"""Integration test for the partition rollover helper (MASTER_PLAN Task 2.8)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.partitioning import ensure_partitions_for_next_n_months

pytestmark = pytest.mark.asyncio


async def test_rollover_creates_future_partitions(db_session: AsyncSession) -> None:
    # Fake clock well beyond the seeded window so the helper actually creates rows.
    fake_now = datetime.datetime(2030, 1, 15, tzinfo=datetime.UTC)
    conn = await db_session.connection()

    ensured = await ensure_partitions_for_next_n_months(conn, n=12, now=fake_now)

    # Current month plus next 12 for each of the 3 partitioned tables.
    assert "downloads_y2030m01" in ensured
    assert "downloads_y2031m01" in ensured  # +12 months
    assert "jobs_y2030m06" in ensured

    result = await conn.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name = 'downloads_y2030m06'"
        )
    )
    assert result.scalar_one() == 1


async def test_rollover_is_idempotent(db_session: AsyncSession) -> None:
    fake_now = datetime.datetime(2031, 3, 10, tzinfo=datetime.UTC)
    conn = await db_session.connection()
    first = await ensure_partitions_for_next_n_months(conn, n=3, now=fake_now)
    # Running again must not error (CREATE TABLE IF NOT EXISTS).
    second = await ensure_partitions_for_next_n_months(conn, n=3, now=fake_now)
    assert first == second
