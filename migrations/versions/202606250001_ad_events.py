"""Sprint 9.5.9 — ``ad_events`` per-event ad analytics table.

Promotes the deferred skeleton from ``migrations/planned/ads_v2_schema.py`` into a live
migration (D-045). ``ad_events`` is monthly RANGE-partitioned by ``created_at`` like
``error_logs`` (D-015/D-016); a rolling 13-month partition window is seeded from the
current month, and the cleanup worker keeps it rolling via
``RUNTIME_PARTITIONED_TABLES``. Additive-only — no existing table is touched. Rows are
written off the delivery hot path (D-052); the ``advertisements`` / ``ad_buttons``
counters remain the source of truth. No foreign keys (analytics-write cheapness; a
deleted ad's events age out with their partition).

Revision ID: 202606250001
Revises: 202606240001
Create Date: 2026-06-25
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from alembic import op

from infrastructure.database.partitioning import initial_partition_statements

revision: str = "202606250001"
down_revision: str | None = "202606240001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CREATE_AD_EVENTS = """
    CREATE TABLE ad_events (
        id               BIGINT GENERATED ALWAYS AS IDENTITY,
        advertisement_id BIGINT NOT NULL,
        user_id          BIGINT,
        event_type       VARCHAR(12) NOT NULL,   -- 'impression' | 'click'
        placement        VARCHAR(30),
        button_id        BIGINT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (id, created_at)
    ) PARTITION BY RANGE (created_at);
"""

_INDEXES: tuple[str, ...] = (
    "CREATE INDEX ix_ad_events_ad ON ad_events (advertisement_id, created_at);",
    "CREATE INDEX ix_ad_events_type_created ON ad_events (event_type, created_at);",
)


def upgrade() -> None:
    op.execute(_CREATE_AD_EVENTS)
    for ddl in _INDEXES:
        op.execute(ddl)
    # Seed a rolling 13-month partition window (current month + next 12), matching the
    # baseline migration's scheme; the cleanup worker extends it thereafter.
    start = datetime.date.today().replace(day=1)
    for statement in initial_partition_statements(["ad_events"], start=start, months=13):
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ad_events CASCADE;")
