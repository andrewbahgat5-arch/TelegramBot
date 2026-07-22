"""V2.1: seed the free/premium plan rows from the live settings (Decision 3).

The entitlement *values* are derived from the existing ``free_*``/``premium_*`` settings
rows rather than hardcoded, so the shadow resolver produces byte-identical limits to the
legacy ``_effective_plan()`` path by construction (any parity mismatch can then only be a
plan-*selection* bug, which is what the soak is meant to catch). A missing settings row
falls back to the shipped V1 default (same numbers as ``202606230002``), so this seed is
safe even on a database where a key was renamed away. The ``free_*``/``premium_*`` settings
stay authoritative until the V2.2 cutover (V2-D-025).

Data-only; down = delete the two rows. Enum/registry keys are the contract; these numbers
are seed data (V2-D-020).

Revision ID: 2026072003
Revises: 2026072002
Create Date: 2026-07-22
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026072003"
down_revision: str | None = "2026072002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# settings key -> V1 shipped default (fallback if the row is absent), matching 202606230002.
_DEFAULTS = {
    "free_daily_limit": 10,
    "premium_daily_limit": 100,
    "download_cooldown_seconds": 30,
    "premium_download_cooldown_seconds": 5,
    "free_max_file_size": 52_428_800,  # 50 MiB
    "premium_max_file_size": 2_147_483_648,  # 2 GiB
}


def _setting_int(bind: sa.engine.Connection, key: str) -> int:
    row = bind.execute(
        sa.text("SELECT value FROM settings WHERE key = :k"), {"k": key}
    ).scalar_one_or_none()
    return int(row) if row is not None else _DEFAULTS[key]


def upgrade() -> None:
    bind = op.get_bind()
    free = {
        "daily_download_limit": _setting_int(bind, "free_daily_limit"),
        "cooldown_seconds": _setting_int(bind, "download_cooldown_seconds"),
        "max_file_size_bytes": _setting_int(bind, "free_max_file_size"),
        "ad_free": False,
        "playlists_enabled": False,
    }
    premium = {
        "daily_download_limit": _setting_int(bind, "premium_daily_limit"),
        "cooldown_seconds": _setting_int(bind, "premium_download_cooldown_seconds"),
        "max_file_size_bytes": _setting_int(bind, "premium_max_file_size"),
        "ad_free": True,
        "playlists_enabled": False,
    }
    bind.execute(
        sa.text(
            "INSERT INTO plans (code, name, is_active, sort_order, entitlements) "
            "VALUES (:code, :name, true, :sort_order, CAST(:entitlements AS JSONB)) "
            "ON CONFLICT (code) DO NOTHING"
        ),
        [
            {"code": "free", "name": "Free", "sort_order": 0, "entitlements": json.dumps(free)},
            {
                "code": "premium",
                "name": "Premium",
                "sort_order": 1,
                "entitlements": json.dumps(premium),
            },
        ],
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM plans WHERE code IN ('free', 'premium')"))
