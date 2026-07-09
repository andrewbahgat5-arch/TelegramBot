"""Language-first ads — ``advertisements.target_language``.

Additive-first per §19.1: one nullable column, no backfill. The admin now picks a
language (English/Arabic) before composing an ad, same as the Broadcast wizard; this
column lets the Advertisements list group/filter campaigns per language. NULL = untargeted
(every ad created before this field, or a deliberately language-agnostic one) — unaffected.

Revision ID: 202607080002
Revises: 202607080001
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607080002"
down_revision: str | None = "202607080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE advertisements ADD COLUMN target_language VARCHAR(10);",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS target_language;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
