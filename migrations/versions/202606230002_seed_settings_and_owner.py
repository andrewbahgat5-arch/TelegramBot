"""Seed the settings key set (Section 13.4) and the Owner user.

Idempotent: every insert uses ON CONFLICT DO NOTHING so re-running is safe
(Section-2 risk mitigation). The Owner's Telegram id comes from the environment
via ``core/config.py`` — never hard-coded.

Revision ID: 202606230002
Revises: 202606230001
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from core.config import Settings

revision: str = "202606230002"
down_revision: str | None = "202606230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (key, value, value_type, description) — MASTER_PLAN Section 13.4 (LOCKED set).
_SEED_SETTINGS: tuple[tuple[str, str, str, str], ...] = (
    ("worker_count", "3", "int", "Display only; actual control via env."),
    ("free_daily_limit", "10", "int", "Free user daily download limit."),
    ("premium_daily_limit", "100", "int", "Premium daily limit (V2)."),
    ("free_max_file_size", "52428800", "int", "Free max file size, 50 MiB (D-005)."),
    ("premium_max_file_size", "2147483648", "int", "Premium max file size, 2 GiB."),
    ("download_cooldown_seconds", "30", "int", "Free user download cooldown."),
    ("premium_download_cooldown_seconds", "5", "int", "Premium cooldown (V2)."),
    ("maintenance_mode", "false", "bool", "Maintenance master switch."),
    ("max_file_size", "2147483648", "int", "Global hard cap on file size."),
    ("max_duration", "14400", "int", "Max media duration in seconds (4 h)."),
    ("rate_limit_messages_per_minute", "30", "int", "Per-user message throttle."),
    ("ads_enabled", "true", "bool", "Ads master switch."),
    ("ads_default_frequency", "1", "int", "Default per-ad frequency override."),
    ("error_log_retention_days", "90", "int", "error_logs retention (D-017)."),
    ("downloads_retention_days", "365", "int", "downloads retention."),
    ("jobs_retention_days", "90", "int", "jobs retention."),
    ("history_page_size", "10", "int", "History pagination size."),
    ("broadcast_chunk_size", "25", "int", "Broadcast per-batch chunk size."),
    ("providers_enabled", '{"ytdlp": true}', "json", "Enabled providers (12.6.7)."),
    ("provider_priority_overrides", "{}", "json", "Provider priority overrides."),
    ("provider_cooldown_seconds", "60", "int", "Degraded-provider cooldown."),
    ("provider_health_check_interval_seconds", "120", "int", "Health check interval."),
    ("provider_failover_enabled", "true", "bool", "Provider failover toggle (D-027)."),
    ("provider_failure_threshold", "3", "int", "Failures before DEGRADED."),
)


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, :value, :value_type, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        [
            {"key": k, "value": v, "value_type": vt, "description": d}
            for (k, v, vt, d) in _SEED_SETTINGS
        ],
    )

    owner_id = Settings().bot_owner_telegram_id  # type: ignore[call-arg]
    bind.execute(
        sa.text(
            "INSERT INTO users (telegram_id, role) VALUES (:telegram_id, 'owner') "
            "ON CONFLICT (telegram_id) DO NOTHING"
        ),
        {"telegram_id": owner_id},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM settings WHERE key = ANY(:keys)"),
        {"keys": [k for (k, _v, _vt, _d) in _SEED_SETTINGS]},
    )
