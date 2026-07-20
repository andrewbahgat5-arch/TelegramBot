"""Widen ``error_logs`` so it can back the Errors/Logs dashboard (DESIGN_MONITORING.md).

The table held only ``error_type/message/traceback/user_id``, which supports none of the
filters the dashboard needs (severity, category, platform, who, which link). Rather than
add a second table, the same rows now carry the classification and the request context —
"Errors" and "Logs" become two filtered VIEWS of one table, so reclassifying an event
type later is a config change instead of a data migration.

All columns are nullable with no backfill: existing rows keep meaning exactly what they
meant, and ``severity`` simply reads NULL for anything written before this revision.

``error_logs`` is monthly RANGE partitioned, so ADD COLUMN propagates to the partitions
automatically; the index is created on the parent and inherited.

Revision ID: 2026071901
Revises: 2026071803
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2026071901"
down_revision: str | None = "2026071803"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    # Routing + the Errors/Logs view split.
    ("severity", sa.String(length=10)),
    ("category", sa.String(length=40)),
    # Request context, denormalised on purpose: the dashboard filters and groups by
    # these constantly, and a join per row to reconstruct them would be wasteful.
    ("platform", sa.String(length=30)),
    ("url", sa.Text()),
    ("url_host", sa.String(length=255)),
    ("username", sa.String(length=64)),
    ("chat_id", sa.BigInteger()),
    # Everything open-ended (quality, format, stage, worker id, duration, cache hit).
    # JSONB so it stays queryable without another migration each time a field is added.
    ("context", postgresql.JSONB(astext_type=sa.Text())),
)


def upgrade() -> None:
    for name, type_ in _COLUMNS:
        op.add_column("error_logs", sa.Column(name, type_, nullable=True))

    # The dashboard's default query is "newest first, filtered by severity", and the
    # 30-day pruning sweeps by created_at — both are served by this index.
    op.create_index(
        "ix_error_logs_severity_created_at",
        "error_logs",
        ["severity", "created_at"],
    )
    # Grouping by platform ("what is failing on instagram this week") is the other
    # query the Logs page runs constantly.
    op.create_index(
        "ix_error_logs_platform_created_at",
        "error_logs",
        ["platform", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_error_logs_platform_created_at", table_name="error_logs")
    op.drop_index("ix_error_logs_severity_created_at", table_name="error_logs")
    for name, _type in reversed(_COLUMNS):
        op.drop_column("error_logs", name)
