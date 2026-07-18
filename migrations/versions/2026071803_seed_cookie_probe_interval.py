"""Seed ``cookie_recovery_probe_interval`` for the EXPIRED-cookie recovery prober.

A separate revision rather than an edit to 2026071802: that one is already applied in
production, so amending it would leave the file describing rows it never inserted.

Revision ID: 2026071803
Revises: 2026071802
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026071803"
down_revision: str | None = "2026071802"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "cookie_recovery_probe_interval"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, :value, :value_type, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {
            "key": _KEY,
            "value": "3600",
            "value_type": "int",
            "description": "Seconds between recovery probes of EXPIRED cookies.",
        },
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM settings WHERE key = :key"), {"key": _KEY})
