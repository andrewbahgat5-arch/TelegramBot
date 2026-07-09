"""Seed placement settings for caption and analysis placements (Sprint 14, Phase 5).

Revision ID: 2026070903
Revises: 2026070902
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026070903"
down_revision: str | None = "2026070902"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEEDS: tuple[tuple[str, str, str, str], ...] = (
    ("ad_placement_caption_enabled", "true", "bool", "Caption-layer ads. ON by default."),
    ("ad_placement_analysis_enabled", "false", "bool", "Ad after URL analysis. Opt-in."),
)


def upgrade() -> None:
    bind = op.get_bind()
    for key, value, value_type, description in _SEEDS:
        bind.execute(
            sa.text(
                "INSERT INTO settings (key, value, value_type, description) "
                "VALUES (:key, :value, :value_type, :description) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"key": key, "value": value, "value_type": value_type, "description": description},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for key, _, _, _ in _SEEDS:
        bind.execute(sa.text("DELETE FROM settings WHERE key = :key"), {"key": key})
