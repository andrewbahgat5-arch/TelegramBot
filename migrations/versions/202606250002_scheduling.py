"""Sprint 9.5.10 — scheduling scaffold: ``scheduled_at`` on broadcasts + advertisements.

Additive-first per §19.1: two nullable columns, no backfill. ``broadcasts.scheduled_at``
lets the BroadcastWorker's due-poller defer a broadcast until it is due;
``advertisements.scheduled_at`` gates a placement ad until its start time. NULL on either
preserves the prior (immediate / always-eligible) behavior. D-053.

Revision ID: 202606250002
Revises: 202606250001
Create Date: 2026-06-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202606250002"
down_revision: str | None = "202606250001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE broadcasts ADD COLUMN scheduled_at TIMESTAMPTZ;",
    "ALTER TABLE advertisements ADD COLUMN scheduled_at TIMESTAMPTZ;",
    # Partial index: only the pending, scheduled rows the due-poller scans.
    "CREATE INDEX ix_broadcasts_scheduled ON broadcasts (scheduled_at) "
    "WHERE status = 'pending' AND scheduled_at IS NOT NULL;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_broadcasts_scheduled;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS scheduled_at;",
    "ALTER TABLE broadcasts DROP COLUMN IF EXISTS scheduled_at;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
