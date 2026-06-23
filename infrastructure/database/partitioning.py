"""Monthly RANGE partition management (MASTER_PLAN D-015, D-016, Task 2.8).

``downloads``, ``jobs``, and ``error_logs`` are monthly RANGE-partitioned by
``created_at``. Partition naming follows the Owner-approved scheme
``{table}_y{YYYY}m{MM}`` (e.g. ``downloads_y2026m07``). The same helpers are used
by the baseline migration (to seed the initial window) and by the cleanup worker's
rollover task (to keep a rolling window ahead of "now").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PARTITIONED_TABLES: tuple[str, ...] = ("downloads", "jobs", "error_logs")


def _first_of_month(value: date) -> date:
    return value.replace(day=1)


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def partition_name(table: str, year: int, month: int) -> str:
    """Return the partition table name for a given month."""
    return f"{table}_y{year}m{month:02d}"


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return ``[start, next_start)`` dates bounding the month's partition range."""
    start = date(year, month, 1)
    next_year, next_month = _add_month(year, month)
    return start, date(next_year, next_month, 1)


def iter_months(start: date, count: int) -> list[tuple[int, int]]:
    """Yield ``(year, month)`` for ``count`` months beginning at ``start``'s month."""
    year, month = start.year, start.month
    months: list[tuple[int, int]] = []
    for _ in range(count):
        months.append((year, month))
        year, month = _add_month(year, month)
    return months


def create_partition_sql(table: str, year: int, month: int) -> str:
    """DDL that creates one monthly partition if it does not already exist."""
    name = partition_name(table, year, month)
    start, end = month_bounds(year, month)
    return (
        f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {table} "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}');"
    )


def initial_partition_statements(
    tables: Sequence[str] = PARTITIONED_TABLES,
    *,
    start: date,
    months: int = 13,
) -> list[str]:
    """All CREATE statements to seed a rolling window for the given tables.

    ``months=13`` covers the current month plus the next twelve, satisfying the
    "rolling 12 months" requirement with one month of lead.
    """
    statements: list[str] = []
    for table in tables:
        for year, month in iter_months(_first_of_month(start), months):
            statements.append(create_partition_sql(table, year, month))
    return statements


async def ensure_partitions_for_next_n_months(
    conn: AsyncConnection,
    n: int = 12,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Create partitions for the current month plus the next ``n`` months.

    Idempotent (CREATE TABLE IF NOT EXISTS). Returns the partition names ensured.
    ``now`` is injectable for deterministic testing with a fake clock.
    """
    current = (now or datetime.now(UTC)).date()
    ensured: list[str] = []
    for table in PARTITIONED_TABLES:
        for year, month in iter_months(_first_of_month(current), n + 1):
            await conn.execute(text(create_partition_sql(table, year, month)))
            ensured.append(partition_name(table, year, month))
    return ensured
