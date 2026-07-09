"""Rich history — ``downloads.source_url`` so the history title can link to the source.

Nullable so old rows stay NULL and render as plain (unlinked) text (item #8).

Revision ID: 2026070905
Revises: 2026070904
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026070905"
down_revision: str | None = "2026070904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE downloads ADD COLUMN source_url TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE downloads DROP COLUMN IF EXISTS source_url;")
