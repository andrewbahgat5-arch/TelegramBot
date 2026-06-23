"""Unit tests for partition naming/SQL helpers (MASTER_PLAN Task 2.8)."""

from __future__ import annotations

import datetime

from infrastructure.database.partitioning import (
    PARTITIONED_TABLES,
    create_partition_sql,
    initial_partition_statements,
    iter_months,
    month_bounds,
    partition_name,
)


def test_partition_name_format() -> None:
    assert partition_name("downloads", 2026, 7) == "downloads_y2026m07"
    assert partition_name("jobs", 2026, 12) == "jobs_y2026m12"


def test_month_bounds_wraps_year() -> None:
    assert month_bounds(2026, 12) == (datetime.date(2026, 12, 1), datetime.date(2027, 1, 1))
    assert month_bounds(2026, 7) == (datetime.date(2026, 7, 1), datetime.date(2026, 8, 1))


def test_iter_months_crosses_year_boundary() -> None:
    assert iter_months(datetime.date(2026, 11, 15), 3) == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
    ]


def test_create_partition_sql_shape() -> None:
    sql = create_partition_sql("downloads", 2026, 7)
    assert "CREATE TABLE IF NOT EXISTS downloads_y2026m07 PARTITION OF downloads" in sql
    assert "FROM ('2026-07-01') TO ('2026-08-01')" in sql


def test_initial_partition_statements_count() -> None:
    statements = initial_partition_statements(
        PARTITIONED_TABLES, start=datetime.date(2026, 1, 10), months=13
    )
    # 3 tables x 13 months.
    assert len(statements) == 39
    assert all("PARTITION OF" in s for s in statements)
