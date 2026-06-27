"""Sprint 9.6 — multi-placement (D-056) + internal ad metadata (D-058).

Additive-first per §19.1.

* ``ad_placements`` one-to-many join table lets an ad occupy several placements at once;
  the scalar ``advertisements.placement`` is retained + dual-read for one deprecation
  window, and this migration backfills one row per existing ad from it.
* ``advertisements.internal_name`` / ``internal_notes`` are admin-only metadata, never on
  any delivery path.

Revision ID: 202606270002
Revises: 202606270001
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202606270002"
down_revision: str | None = "202606270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    """CREATE TABLE ad_placements (
        advertisement_id BIGINT NOT NULL REFERENCES advertisements (id) ON DELETE CASCADE,
        placement        VARCHAR(30) NOT NULL,
        PRIMARY KEY (advertisement_id, placement)
    );""",
    "CREATE INDEX ix_ad_placements_placement ON ad_placements (placement);",
    # Backfill one row per existing ad from the scalar placement column.
    "INSERT INTO ad_placements (advertisement_id, placement) "
    "SELECT id, placement FROM advertisements ON CONFLICT DO NOTHING;",
    "ALTER TABLE advertisements ADD COLUMN internal_name VARCHAR(120);",
    "ALTER TABLE advertisements ADD COLUMN internal_notes TEXT;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS internal_notes;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS internal_name;",
    "DROP TABLE IF EXISTS ad_placements;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
