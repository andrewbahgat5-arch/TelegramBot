"""Sprint 9.5 — Ads v2 schema (advertisements expansion).

Additive-first per §19.1. Adds rich-content + placement + audience columns to
``advertisements``, the ``ad_buttons`` / ``ad_audience_rules`` / ``audience_segments``
/ ``audience_segment_members`` tables, ``broadcasts.advertisement_id``, the
placement-selection index, and seeds the §13.6 settings keys.

No data backfill is required: ``AdService`` dual-reads legacy ads — it falls back to
the single ``(button_text, button_url)`` when an ad has no ``ad_buttons`` rows, and to
``target_role`` when an ad has no audience rules (D-043 deprecation window). The
optional ``ad_events`` analytics table is deferred to task 9.5.9 (skeleton kept in
``migrations/planned/``).

Revision ID: 202606240001
Revises: 202606230002
Create Date: 2026-06-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606240001"
down_revision: str | None = "202606230002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# §13.6 settings keys (key, value, value_type, description).
_ADS_V2_SETTINGS: tuple[tuple[str, str, str, str], ...] = (
    ("ads_storage_chat_id", "0", "int", "Bot-owned storage channel for copy-mode ads (0=off)."),
    ("ad_placement_post_download_enabled", "true", "bool", "Compat placement (Sprint 9). ON."),
    ("ad_placement_video_delivery_enabled", "false", "bool", "Persistent ad under video. Opt-in."),
    ("ad_placement_audio_delivery_enabled", "false", "bool", "Persistent ad under audio. Opt-in."),
    ("ad_placement_quality_select_enabled", "false", "bool", "Ad on quality-select. Opt-in."),
    ("ad_placement_home_enabled", "false", "bool", "Ad on home/start. Opt-in."),
    ("ad_placement_history_enabled", "false", "bool", "Ad on history pages. Opt-in."),
)


_UPGRADE_DDL: tuple[str, ...] = (
    # advertisements: additive Ads v2 columns (one ALTER per statement).
    "ALTER TABLE advertisements ADD COLUMN placement VARCHAR(30) "
    "NOT NULL DEFAULT 'post_download';",
    "ALTER TABLE advertisements ADD COLUMN delivery_mode VARCHAR(10) "
    "NOT NULL DEFAULT 'fields';",
    "ALTER TABLE advertisements ADD COLUMN storage_chat_id BIGINT;",
    "ALTER TABLE advertisements ADD COLUMN storage_message_id BIGINT;",
    "ALTER TABLE advertisements ADD COLUMN parse_mode VARCHAR(10);",
    "ALTER TABLE advertisements ADD COLUMN audience_mode VARCHAR(10) "
    "NOT NULL DEFAULT 'all';",
    # ad_buttons.
    """CREATE TABLE ad_buttons (
        id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        advertisement_id BIGINT NOT NULL REFERENCES advertisements (id) ON DELETE CASCADE,
        text             VARCHAR(100) NOT NULL,
        url              TEXT,
        row              SMALLINT NOT NULL DEFAULT 0,
        position         SMALLINT NOT NULL DEFAULT 0,
        clicks           BIGINT NOT NULL DEFAULT 0
    );""",
    "CREATE INDEX ix_ad_buttons_ad ON ad_buttons (advertisement_id, row, position);",
    # ad_audience_rules.
    """CREATE TABLE ad_audience_rules (
        id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        advertisement_id BIGINT NOT NULL REFERENCES advertisements (id) ON DELETE CASCADE,
        effect           VARCHAR(10) NOT NULL,
        dimension        VARCHAR(20) NOT NULL,
        value            VARCHAR(64) NOT NULL
    );""",
    "CREATE INDEX ix_ad_audience_rules_ad ON ad_audience_rules (advertisement_id);",
    "CREATE INDEX ix_ad_audience_rules_dim ON ad_audience_rules (dimension, value);",
    # audience_segments + members.
    """CREATE TABLE audience_segments (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        name        VARCHAR(100) NOT NULL UNIQUE,
        description TEXT,
        created_by  BIGINT NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );""",
    """CREATE TABLE audience_segment_members (
        segment_id BIGINT NOT NULL REFERENCES audience_segments (id) ON DELETE CASCADE,
        user_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        PRIMARY KEY (segment_id, user_id)
    );""",
    "CREATE INDEX ix_audience_segment_members_user ON audience_segment_members (user_id);",
    # broadcasts link + placement selection index.
    "ALTER TABLE broadcasts ADD COLUMN advertisement_id BIGINT "
    "REFERENCES advertisements (id) ON DELETE SET NULL;",
    "CREATE INDEX ix_ads_placement_active_priority "
    "ON advertisements (placement, is_active, priority DESC);",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_ads_placement_active_priority;",
    "ALTER TABLE broadcasts DROP COLUMN IF EXISTS advertisement_id;",
    "DROP TABLE IF EXISTS audience_segment_members;",
    "DROP TABLE IF EXISTS audience_segments;",
    "DROP TABLE IF EXISTS ad_audience_rules;",
    "DROP TABLE IF EXISTS ad_buttons;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS placement;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS delivery_mode;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS storage_chat_id;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS storage_message_id;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS parse_mode;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS audience_mode;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)

    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, :value, :value_type, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        [
            {"key": k, "value": v, "value_type": vt, "description": d}
            for (k, v, vt, d) in _ADS_V2_SETTINGS
        ],
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM settings WHERE key = ANY(:keys)"),
        {"keys": [k for (k, _v, _vt, _d) in _ADS_V2_SETTINGS]},
    )
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
