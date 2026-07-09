"""History display sprint — ``downloads.title``.

Additive-first per §19.1: one nullable column, no backfill. Stores the media title
(``MediaInfo.title``) alongside the existing denormalized platform/format/quality so
history rows can show a human-readable title + platform emoji instead of a bare
platform/quality/format line.

Revision ID: 202607080001
Revises: 202607070001
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607080001"
down_revision: str | None = "202607070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = ("ALTER TABLE downloads ADD COLUMN title TEXT;",)

_DOWNGRADE_DDL: tuple[str, ...] = ("ALTER TABLE downloads DROP COLUMN IF EXISTS title;",)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
