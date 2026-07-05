"""Unit tests for services/user_health.py — the batch status checker (Sprint 13.5)."""

from __future__ import annotations

import datetime

import pytest

from services.user_health import (
    HealthReport,
    ProbeOutcome,
    UserHealthChecker,
)

pytestmark = pytest.mark.asyncio


class _FakeProber:
    """Returns a scripted outcome per telegram id (default ACTIVE)."""

    def __init__(self, outcomes: dict[int, ProbeOutcome]) -> None:
        self.outcomes = outcomes
        self.probed: list[int] = []

    async def probe(self, telegram_id: int) -> ProbeOutcome:
        self.probed.append(telegram_id)
        return self.outcomes.get(telegram_id, ProbeOutcome.ACTIVE)


class _FakeStore:
    """Minimal UserHealthStore: tracks marks and hands out ids once."""

    def __init__(self, ids: list[int]) -> None:
        self._ids = ids
        self.marked: dict[int, str] = {}

    async def count_all(self) -> int:
        return len(self._ids)

    async def get_unchecked_ids(self, *, limit: int = 100) -> list[int]:
        # Unmarked ids first (unchecked), then already-marked (oldest-first proxy).
        unmarked = [i for i in self._ids if i not in self.marked]
        marked = [i for i in self._ids if i in self.marked]
        return (unmarked + marked)[:limit]

    async def mark_active(self, telegram_id: int) -> None:
        self.marked[telegram_id] = "active"

    async def mark_blocked(self, telegram_id: int) -> None:
        self.marked[telegram_id] = "blocked"

    async def mark_deleted(self, telegram_id: int) -> None:
        self.marked[telegram_id] = "deleted"


def _counter_clock() -> list[datetime.datetime]:
    base = datetime.datetime(2026, 7, 5, tzinfo=datetime.UTC)
    return [base + datetime.timedelta(seconds=i) for i in range(200)]


def _checker(prober: _FakeProber, store: _FakeStore) -> UserHealthChecker:
    ticks = iter(_counter_clock())
    return UserHealthChecker(
        prober=prober,
        store=store,
        chunk_delay_seconds=0.0,
        now=lambda: next(ticks),
        sleep=_noop_sleep,
    )


async def _noop_sleep(delay: float) -> None:
    return None


async def test_check_batch_marks_each_outcome() -> None:
    prober = _FakeProber({1: ProbeOutcome.ACTIVE, 2: ProbeOutcome.BLOCKED, 3: ProbeOutcome.DELETED})
    store = _FakeStore([1, 2, 3])
    report = await _checker(prober, store).check_batch([1, 2, 3])

    assert isinstance(report, HealthReport)
    assert (report.active, report.blocked, report.deleted, report.errors) == (1, 1, 1, 0)
    assert report.total_checked == 3
    assert store.marked == {1: "active", 2: "blocked", 3: "deleted"}


async def test_check_batch_error_leaves_user_unmarked() -> None:
    prober = _FakeProber({9: ProbeOutcome.ERROR})
    store = _FakeStore([9])
    report = await _checker(prober, store).check_batch([9])

    assert report.errors == 1
    assert store.marked == {}  # unmarked so it is retried next sweep


async def test_check_all_sweeps_everyone_once_in_chunks() -> None:
    prober = _FakeProber({2: ProbeOutcome.BLOCKED})
    store = _FakeStore([1, 2, 3, 4, 5])
    seen: list[tuple[int, int]] = []

    async def progress(checked: int, total: int) -> None:
        seen.append((checked, total))

    report = await _checker(prober, store).check_all(batch_size=2, progress_callback=progress)

    assert report.total_checked == 5
    assert report.blocked == 1 and report.active == 4
    assert sorted(prober.probed) == [1, 2, 3, 4, 5]  # each probed exactly once
    assert seen[-1] == (5, 5)  # progress ends at 100%


async def test_check_all_empty_store_is_noop() -> None:
    report = await _checker(_FakeProber({}), _FakeStore([])).check_all(batch_size=10)
    assert report.total_checked == 0
    assert report.duration_seconds >= 0.0
