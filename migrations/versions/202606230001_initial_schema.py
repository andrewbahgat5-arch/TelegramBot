"""Initial V1 schema: tables 1-12, monthly partitions, indexes, FKs.

Creates the entire LOCKED V1 schema (MASTER_PLAN Section 10) in one baseline
migration. ``downloads``, ``jobs`` and ``error_logs`` are monthly RANGE-partitioned
(D-015, D-016); a rolling 13-month window of partitions is seeded from the current
month. Indexes are created on the partitioned parents so they cascade to every
current and future partition. All FK ON DELETE actions follow Section 10.14.

Revision ID: 202606230001
Revises:
Create Date: 2026-06-23
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from alembic import op

from infrastructure.database.partitioning import (
    PARTITIONED_TABLES,
    initial_partition_statements,
)

revision: str = "202606230001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_TABLES_DDL: tuple[str, ...] = (
    # 1. users
    """
    CREATE TABLE users (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        username VARCHAR(255),
        first_name VARCHAR(255),
        language VARCHAR(10),
        role VARCHAR(20) NOT NULL DEFAULT 'user',
        is_premium BOOLEAN NOT NULL DEFAULT false,
        premium_expires_at TIMESTAMPTZ,
        is_banned BOOLEAN NOT NULL DEFAULT false,
        banned_at TIMESTAMPTZ,
        ban_reason VARCHAR(500),
        daily_download_count INTEGER NOT NULL DEFAULT 0,
        daily_download_count_reset_date DATE NOT NULL DEFAULT CURRENT_DATE,
        total_downloads BIGINT NOT NULL DEFAULT 0,
        last_activity_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_users_telegram_id UNIQUE (telegram_id)
    );
    """,
    # 2. media_metadata
    """
    CREATE TABLE media_metadata (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        platform VARCHAR(50) NOT NULL,
        video_id VARCHAR(255) NOT NULL,
        title TEXT NOT NULL,
        duration INTEGER,
        thumbnail_url TEXT,
        source_url TEXT NOT NULL,
        metadata_json JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_media_platform_video UNIQUE (platform, video_id)
    );
    """,
    # 3. cached_files
    """
    CREATE TABLE cached_files (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        media_id BIGINT NOT NULL REFERENCES media_metadata(id) ON DELETE CASCADE,
        format VARCHAR(50) NOT NULL,
        quality VARCHAR(20) NOT NULL,
        telegram_file_id VARCHAR(255) NOT NULL,
        telegram_unique_file_id VARCHAR(255) NOT NULL,
        file_size BIGINT,
        usage_count BIGINT NOT NULL DEFAULT 0,
        last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_cached_media_format_quality UNIQUE (media_id, format, quality)
    );
    """,
    # 5. jobs (partitioned) — created before downloads so logical refs are clear
    """
    CREATE TABLE jobs (
        id UUID NOT NULL,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        media_id BIGINT NOT NULL REFERENCES media_metadata(id) ON DELETE RESTRICT,
        format VARCHAR(50) NOT NULL,
        quality VARCHAR(20) NOT NULL,
        worker_kind VARCHAR(30) NOT NULL DEFAULT 'download',
        priority INTEGER NOT NULL DEFAULT 1000,
        retry_count INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(30) NOT NULL DEFAULT 'created',
        error_message TEXT,
        correlation_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        finished_at TIMESTAMPTZ,
        PRIMARY KEY (id, created_at)
    ) PARTITION BY RANGE (created_at);
    """,
    # 4. downloads (partitioned)
    """
    CREATE TABLE downloads (
        id BIGINT GENERATED ALWAYS AS IDENTITY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        cached_file_id BIGINT REFERENCES cached_files(id) ON DELETE SET NULL,
        platform VARCHAR(50) NOT NULL,
        format VARCHAR(50) NOT NULL,
        quality VARCHAR(20) NOT NULL,
        file_size BIGINT,
        status VARCHAR(20) NOT NULL DEFAULT 'completed',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (id, created_at)
    ) PARTITION BY RANGE (created_at);
    """,
    # 12. error_logs (partitioned)
    """
    CREATE TABLE error_logs (
        id BIGINT GENERATED ALWAYS AS IDENTITY,
        user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        job_id UUID,
        correlation_id UUID,
        error_type VARCHAR(30) NOT NULL,
        message TEXT NOT NULL,
        traceback TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (id, created_at)
    ) PARTITION BY RANGE (created_at);
    """,
    # 6. active_downloads
    """
    CREATE TABLE active_downloads (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        media_id BIGINT NOT NULL REFERENCES media_metadata(id) ON DELETE CASCADE,
        format VARCHAR(50) NOT NULL,
        quality VARCHAR(20) NOT NULL,
        job_id UUID NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_active_media_format_quality UNIQUE (media_id, format, quality)
    );
    """,
    # 7. job_waiters
    """
    CREATE TABLE job_waiters (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        job_id UUID NOT NULL,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        correlation_id UUID,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_job_waiter UNIQUE (job_id, user_id)
    );
    """,
    # 8. broadcasts
    """
    CREATE TABLE broadcasts (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        target_language VARCHAR(10),
        target_role VARCHAR(20),
        message_text TEXT NOT NULL,
        expected_total INTEGER NOT NULL DEFAULT 0,
        total_sent INTEGER NOT NULL DEFAULT 0,
        total_failed INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    );
    """,
    # 9. advertisements
    """
    CREATE TABLE advertisements (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        type VARCHAR(20) NOT NULL DEFAULT 'text',
        content_text TEXT,
        content_media_file_id VARCHAR(255),
        button_text VARCHAR(100),
        button_url TEXT,
        target_role VARCHAR(20),
        show_every_n_downloads INTEGER NOT NULL DEFAULT 1,
        is_active BOOLEAN NOT NULL DEFAULT true,
        priority INTEGER NOT NULL DEFAULT 0,
        impressions BIGINT NOT NULL DEFAULT 0,
        clicks BIGINT NOT NULL DEFAULT 0,
        created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    # 10. settings
    """
    CREATE TABLE settings (
        key VARCHAR(100) PRIMARY KEY,
        value TEXT NOT NULL,
        value_type VARCHAR(20) NOT NULL DEFAULT 'string',
        description TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL
    );
    """,
    # 11. user_preferences
    """
    CREATE TABLE user_preferences (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        notifications_enabled BOOLEAN NOT NULL DEFAULT true,
        preferred_language VARCHAR(10),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_user_preferences_user UNIQUE (user_id)
    );
    """,
)

_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX ix_users_role ON users (role);",
    "CREATE INDEX ix_users_is_premium ON users (is_premium);",
    "CREATE INDEX ix_users_is_banned ON users (is_banned);",
    "CREATE INDEX ix_users_last_activity ON users (last_activity_at);",
    "CREATE INDEX ix_users_created_at ON users (created_at);",
    "CREATE INDEX ix_media_platform ON media_metadata (platform);",
    "CREATE INDEX ix_media_created_at ON media_metadata (created_at);",
    "CREATE INDEX ix_cached_media_id ON cached_files (media_id);",
    "CREATE INDEX ix_cached_last_used ON cached_files (last_used_at);",
    "CREATE INDEX ix_cached_usage_count ON cached_files (usage_count);",
    "CREATE INDEX ix_downloads_user_id ON downloads (user_id);",
    "CREATE INDEX ix_downloads_user_created ON downloads (user_id, created_at DESC);",
    "CREATE INDEX ix_downloads_platform ON downloads (platform);",
    "CREATE INDEX ix_downloads_created_at ON downloads (created_at);",
    "CREATE INDEX ix_jobs_user_id ON jobs (user_id);",
    "CREATE INDEX ix_jobs_status ON jobs (status);",
    "CREATE INDEX ix_jobs_media_id ON jobs (media_id);",
    "CREATE INDEX ix_jobs_status_priority ON jobs (status, priority, created_at);",
    "CREATE INDEX ix_jobs_correlation_id ON jobs (correlation_id);",
    "CREATE INDEX ix_active_job_id ON active_downloads (job_id);",
    "CREATE INDEX ix_job_waiters_job ON job_waiters (job_id);",
    "CREATE INDEX ix_job_waiters_user ON job_waiters (user_id);",
    "CREATE INDEX ix_broadcasts_created_at ON broadcasts (created_at);",
    "CREATE INDEX ix_broadcasts_status ON broadcasts (status);",
    "CREATE INDEX ix_ads_active_priority_role "
    "ON advertisements (is_active, priority DESC, target_role);",
    "CREATE INDEX ix_ads_target_role ON advertisements (target_role);",
    "CREATE INDEX ix_errors_user_id ON error_logs (user_id);",
    "CREATE INDEX ix_errors_job_id ON error_logs (job_id);",
    "CREATE INDEX ix_errors_type ON error_logs (error_type);",
    "CREATE INDEX ix_errors_created_at ON error_logs (created_at);",
    "CREATE INDEX ix_errors_correlation_id ON error_logs (correlation_id);",
)

# Tables in drop order (reverse of create; respects FK dependencies).
_DROP_ORDER: tuple[str, ...] = (
    "user_preferences",
    "settings",
    "advertisements",
    "broadcasts",
    "job_waiters",
    "active_downloads",
    "error_logs",
    "downloads",
    "jobs",
    "cached_files",
    "media_metadata",
    "users",
)


def upgrade() -> None:
    for ddl in _TABLES_DDL:
        op.execute(ddl)
    for ddl in _INDEX_DDL:
        op.execute(ddl)
    # Seed a rolling 13-month partition window (current month + next 12).
    start = datetime.date.today().replace(day=1)
    for statement in initial_partition_statements(
        PARTITIONED_TABLES, start=start, months=13
    ):
        op.execute(statement)


def downgrade() -> None:
    for table in _DROP_ORDER:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
