"""Seed the V2 feature-flag settings rows, all OFF (VERSION_2_MASTER_PLAN §5.8).

Every major V2 feature ships behind an individually toggleable flag (V2-D-031). The
flags are plain ``bool`` rows in the LOCKED ``settings`` table, read through the
cached ``SettingsService`` and toggled from the admin panel — no new infrastructure.
They are seeded ``false`` so the mere presence of this migration changes no behavior;
each feature's sprint flips its flag on per the staged-rollout plan. ``FeatureFlagService``
reads a missing row as off, so this seed is convenience — the app is safe before it runs.

Revision ID: 2026072001
Revises: 2026071901
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026072001"
down_revision: str | None = "2026071901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (key, description) — every flag is value "false", value_type "bool".
_FLAGS: tuple[tuple[str, str], ...] = (
    ("feature_subscriptions_enabled", "V2: entitlement path (off => legacy is_premium)."),
    ("feature_multilink_enabled", "V2: multi-link batch admission (off => first URL only)."),
    ("feature_premium_quality_gating_enabled", "V2: 2K/4K + lossless-audio plan gating."),
    ("feature_ad_analytics_enabled", "V2: ad_events emission (counters always stay on)."),
    ("feature_expiry_notifications_enabled", "V2: subscription-expiry notifier job."),
    ("analyzer_raw_metadata_enabled", "V2: raw extractor-metadata retention under _raw namespace."),
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, 'false', 'bool', :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        [{"key": key, "description": description} for key, description in _FLAGS],
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM settings WHERE key = :key"),
        [{"key": key} for key, _ in _FLAGS],
    )
