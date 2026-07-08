"""UX sprint #10 — fair ad rotation: ``advertisements.last_shown_at``.

Additive-first per §19.1: one nullable column, no backfill. Records when an ad was last
delivered so the placement selector can prefer the least-recently-shown ad among equal-
priority candidates that are all due (a deterministic, self-correcting round-robin). NULL
= never shown, which sorts first. A composite index backs the selection ORDER BY
(``is_active`` filtered, ``priority`` DESC, ``last_shown_at`` ASC).

Revision ID: 202607070001
Revises: 202607060001
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607070001"
down_revision: str | None = "202607060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE advertisements ADD COLUMN last_shown_at TIMESTAMPTZ;",
    # Backs the fair-rotation selection order (priority tier, then least-recently-shown).
    "CREATE INDEX ix_ads_active_priority_last_shown ON advertisements "
    "(priority DESC, last_shown_at ASC, id ASC) WHERE is_active;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP INDEX IF EXISTS ix_ads_active_priority_last_shown;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS last_shown_at;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
