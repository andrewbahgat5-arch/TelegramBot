"""Rich history — ``downloads.duration_seconds`` + ``downloads.size_bytes``.

Nullable columns so old rows stay NULL and render cleanly (Phase 1.3).

Revision ID: 2026070901
Revises: 202607080002
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026070901"
down_revision: str | None = "202607080002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE downloads ADD COLUMN duration_seconds INTEGER;",
    "ALTER TABLE downloads ADD COLUMN size_bytes BIGINT;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE downloads DROP COLUMN IF EXISTS size_bytes;",
    "ALTER TABLE downloads DROP COLUMN IF EXISTS duration_seconds;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
