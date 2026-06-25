"""Unit tests for the readiness checker (MASTER_PLAN Task 10.4, Section 15.7)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from api.readiness import ReadinessChecker

pytestmark = pytest.mark.asyncio


async def _ok() -> None:
    return None


def _depth(value: int) -> Any:
    async def probe() -> int:
        return value

    return probe


async def test_all_checks_pass() -> None:
    checker = ReadinessChecker(
        db_ping=_ok,
        redis_ping=_ok,
        queue_depth=_depth(5),
        active_workers=_depth(2),
    )
    report = await checker.check()
    assert report.ready is True
    assert set(report.checks) == {"database", "redis", "queue", "workers"}
    assert all(r.ok for r in report.checks.values())


async def test_no_workers_is_not_ready() -> None:
    checker = ReadinessChecker(
        db_ping=_ok, redis_ping=_ok, queue_depth=_depth(0), active_workers=_depth(0)
    )
    report = await checker.check()
    assert report.ready is False
    assert report.checks["workers"].ok is False
    assert report.checks["queue"].ok is True  # depth 0 is valid


async def test_db_failure_marks_unready() -> None:
    async def boom() -> None:
        raise ConnectionError("db down")

    checker = ReadinessChecker(
        db_ping=boom, redis_ping=_ok, queue_depth=_depth(1), active_workers=_depth(1)
    )
    report = await checker.check()
    assert report.ready is False
    assert report.checks["database"].ok is False
    assert "db down" in report.checks["database"].detail


async def test_slow_ping_times_out() -> None:
    async def slow() -> None:
        await asyncio.sleep(1.0)

    checker = ReadinessChecker(
        db_ping=slow,
        redis_ping=_ok,
        queue_depth=_depth(1),
        active_workers=_depth(1),
        timeout_seconds=0.05,
    )
    report = await checker.check()
    assert report.ready is False
    assert report.checks["database"].ok is False
    assert "exceeded" in report.checks["database"].detail
