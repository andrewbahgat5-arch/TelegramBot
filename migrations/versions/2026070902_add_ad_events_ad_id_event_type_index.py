"""Add index on ad_events (advertisement_id, event_type) for stats aggregation.

Partitioned table — Postgres propagates the index to existing and future partitions.

Revision ID: 2026070902
Revises: 2026070901
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026070902"
down_revision: str | None = "2026070901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_ad_events_ad_id_event_type",
        "ad_events",
        ["advertisement_id", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_ad_events_ad_id_event_type", table_name="ad_events")
