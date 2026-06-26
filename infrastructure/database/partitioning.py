"""Monthly RANGE partition management (MASTER_PLAN D-015, D-016, Task 2.8).

``downloads``, ``jobs``, and ``error_logs`` are monthly RANGE-partitioned by
``created_at``. Partition naming follows the Owner-approved scheme
``{table}_y{YYYY}m{MM}`` (e.g. ``downloads_y2026m07``). The same helpers are used
by the baseline migration (to seed the initial window) and by the cleanup worker's
rollover task (to keep a rolling window ahead of "now").
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PARTITIONED_TABLES: tuple[str, ...] = ("downloads", "jobs", "error_logs")

# ``ad_events`` (Sprint 9.5.9) is monthly-partitioned too, but it is created by a LATER
# migration (202606250001), so it must NOT be in ``PARTITIONED_TABLES`` — the baseline
# migration (202606230001) seeds that set's partitions before ``ad_events`` exists. The
# runtime rollover/retention paths use this fuller set so ``ad_events`` partitions keep
# rolling. (``ad_events`` has no retention key, so it is not auto-dropped — see D-052.)
RUNTIME_PARTITIONED_TABLES: tuple[str, ...] = (*PARTITIONED_TABLES, "ad_events")

# Matches the ``y{YYYY}m{MM}`` suffix of a partition name (possibly schema-qualified).
_PARTITION_SUFFIX_RE = re.compile(r"_y(\d{4})m(\d{2})$")


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
    for table in RUNTIME_PARTITIONED_TABLES:
        for year, month in iter_months(_first_of_month(current), n + 1):
            await conn.execute(text(create_partition_sql(table, year, month)))
            ensured.append(partition_name(table, year, month))
    return ensured


def partitions_to_drop(
    existing: Sequence[str], *, table: str, cutoff_year: int, cutoff_month: int
) -> list[str]:
    """Names among ``existing`` that belong to ``table`` and predate the cutoff month.

    Pure helper (testable without a database). A partition for month ``(y, m)`` is
    dropped when ``(y, m) < (cutoff_year, cutoff_month)``. Names not matching the
    ``{table}_y…m…`` scheme are ignored.
    """
    cutoff = (cutoff_year, cutoff_month)
    selected: list[str] = []
    for name in existing:
        bare = name.split(".")[-1]
        if not bare.startswith(f"{table}_y"):
            continue
        match = _PARTITION_SUFFIX_RE.search(bare)
        if match is None:
            continue
        if (int(match.group(1)), int(match.group(2))) < cutoff:
            selected.append(name)
    return selected


async def list_partitions(conn: AsyncConnection, table: str) -> list[str]:
    """Return the child partition names of ``table`` (schema-qualified)."""
    result = await conn.execute(
        text(
            "SELECT inhrelid::regclass::text FROM pg_inherits "
            "WHERE inhparent = CAST(:table AS regclass)"
        ),
        {"table": table},
    )
    return [row[0] for row in result]


async def drop_partitions_older_than(
    conn: AsyncConnection, table: str, *, cutoff: date
) -> list[str]:
    """Drop ``table`` partitions for months strictly before ``cutoff``'s month (D-015).

    Retention by partition drop is O(1) per month and reclaims storage immediately,
    unlike a row-by-row DELETE. Returns the dropped partition names.
    """
    existing = await list_partitions(conn, table)
    to_drop = partitions_to_drop(
        existing, table=table, cutoff_year=cutoff.year, cutoff_month=cutoff.month
    )
    for name in to_drop:
        await conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
    return to_drop
