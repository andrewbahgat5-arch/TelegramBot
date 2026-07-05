"""Sprint 13.5 — blocked-bot / deleted-account detection flags on ``users``.

Additive-first per §19.1. Adds two boolean health flags plus the timestamp of the
last Telegram-API status probe, and a partial-friendly index on
``status_checked_at`` so ``get_unchecked_ids`` (NULLS FIRST / oldest first) is cheap.

Revision ID: 202607050001
Revises: 202606270002
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607050001"
down_revision: str | None = "202606270002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN bot_blocked BOOLEAN NOT NULL DEFAULT FALSE;",
    "ALTER TABLE users ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE;",
    "ALTER TABLE users ADD COLUMN status_checked_at TIMESTAMPTZ;",
    "CREATE INDEX ix_users_status_checked_at ON users (status_checked_at NULLS FIRST);",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_users_status_checked_at;",
    "ALTER TABLE users DROP COLUMN IF EXISTS status_checked_at;",
    "ALTER TABLE users DROP COLUMN IF EXISTS is_deleted;",
    "ALTER TABLE users DROP COLUMN IF EXISTS bot_blocked;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
