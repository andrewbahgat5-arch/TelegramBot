"""User Settings toggles — ``auto_download_small`` + ``hide_title`` on user_preferences.

Per-user preferences for the Settings screen (item #10, phase 1). Both default OFF so
current behavior is preserved. Meta/description toggles land in a later phase once
delivered captions carry that metadata.

Revision ID: 2026070906
Revises: 2026070905
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026070906"
down_revision: str | None = "2026070905"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE user_preferences ADD COLUMN auto_download_small BOOLEAN NOT NULL DEFAULT false;",
    "ALTER TABLE user_preferences ADD COLUMN hide_title BOOLEAN NOT NULL DEFAULT false;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE user_preferences DROP COLUMN IF EXISTS hide_title;",
    "ALTER TABLE user_preferences DROP COLUMN IF EXISTS auto_download_small;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
