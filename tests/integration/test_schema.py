"""Schema introspection tests — actual DB vs MASTER_PLAN Section 10 (Task 2.9)."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio

EXPECTED_TABLES = {
    "users",
    "media_metadata",
    "cached_files",
    "downloads",
    "jobs",
    "active_downloads",
    "job_waiters",
    "broadcasts",
    "advertisements",
    "settings",
    "error_logs",
    "user_preferences",
}

PARTITIONED_TABLES = {"downloads", "jobs", "error_logs"}

# (table, column, ON DELETE confdeltype) per Section 10.14. a=no action,
# r=restrict, c=cascade, n=set null.
EXPECTED_FK_DELETE = {
    ("downloads", "user_id"): "c",
    ("downloads", "cached_file_id"): "n",
    ("jobs", "user_id"): "c",
    ("jobs", "media_id"): "r",
    ("cached_files", "media_id"): "c",
    ("active_downloads", "media_id"): "c",
    ("broadcasts", "created_by"): "r",
    ("advertisements", "created_by"): "r",
    ("error_logs", "user_id"): "n",
    ("user_preferences", "user_id"): "c",
    ("job_waiters", "user_id"): "c",
    ("settings", "updated_by"): "n",
}

EXPECTED_INDEXES = {
    "ix_users_role",
    "ix_users_is_premium",
    "ix_users_is_banned",
    "ix_users_last_activity",
    "ix_users_created_at",
    "ix_media_platform",
    "ix_media_created_at",
    "ix_cached_media_id",
    "ix_cached_last_used",
    "ix_cached_usage_count",
    "ix_downloads_user_id",
    "ix_downloads_user_created",
    "ix_downloads_platform",
    "ix_downloads_created_at",
    "ix_jobs_user_id",
    "ix_jobs_status",
    "ix_jobs_media_id",
    "ix_jobs_status_priority",
    "ix_jobs_correlation_id",
    "ix_active_job_id",
    "ix_job_waiters_job",
    "ix_job_waiters_user",
    "ix_broadcasts_created_at",
    "ix_broadcasts_status",
    "ix_ads_active_priority_role",
    "ix_ads_target_role",
    "ix_errors_user_id",
    "ix_errors_job_id",
    "ix_errors_type",
    "ix_errors_created_at",
    "ix_errors_correlation_id",
}


async def test_all_base_tables_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' "
            "AND table_name !~ '_y20[0-9]{2}m[0-9]{2}$'"
        )
    )
    names = {row[0] for row in result}
    assert EXPECTED_TABLES <= names


async def test_partitioned_tables_are_partitioned(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT c.relname FROM pg_partitioned_table p JOIN pg_class c ON c.oid = p.partrelid")
    )
    partitioned = {row[0] for row in result}
    assert PARTITIONED_TABLES <= partitioned


async def test_rolling_partition_window_seeded(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name ~ '_y20[0-9]{2}m[0-9]{2}$'"
        )
    )
    # 3 partitioned tables x 13-month window.
    assert result.scalar_one() >= 39


async def test_users_columns_match_spec(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='users'"
        )
    )
    cols = {row[0]: (row[1], row[2]) for row in result}
    assert cols["telegram_id"] == ("bigint", "NO")
    assert cols["role"] == ("character varying", "NO")
    assert cols["is_banned"] == ("boolean", "NO")
    assert cols["daily_download_count"] == ("integer", "NO")
    assert cols["daily_download_count_reset_date"] == ("date", "NO")
    assert cols["premium_expires_at"] == ("timestamp with time zone", "YES")
    assert cols["total_downloads"] == ("bigint", "NO")


async def test_foreign_key_ondelete_actions(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT cl.relname, att.attname, con.confdeltype::text "
            "FROM pg_constraint con "
            "JOIN pg_class cl ON cl.oid = con.conrelid "
            "JOIN unnest(con.conkey) AS cols(attnum) ON true "
            "JOIN pg_attribute att ON att.attrelid = con.conrelid "
            "AND att.attnum = cols.attnum "
            "WHERE con.contype = 'f'"
        )
    )
    actual = {(row[0], row[1]): row[2] for row in result}
    for key, expected in EXPECTED_FK_DELETE.items():
        assert actual.get(key) == expected, f"FK {key} expected {expected}, got {actual.get(key)}"


async def test_expected_indexes_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    )
    names = {row[0] for row in result}
    missing = EXPECTED_INDEXES - names
    assert not missing, f"missing indexes: {missing}"


async def test_seeded_settings_present_with_types(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT key, value_type FROM settings"))
    types = {row[0]: row[1] for row in result}
    assert types["free_daily_limit"] == "int"
    assert types["maintenance_mode"] == "bool"
    assert types["providers_enabled"] == "json"
    assert len(types) >= 24
