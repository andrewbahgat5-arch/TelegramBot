"""Sprint 9.5 — Ads v2: DEFERRED analytics table only (PLANNED / NON-WIRED SKELETON).

================================================================================
THIS IS NOT A LIVE MIGRATION. DO NOT RUN.
================================================================================
The Ads v2 core schema (advertisements ALTERs, ad_buttons, ad_audience_rules,
audience_segments, audience_segment_members, broadcasts.advertisement_id, the
placement index, §13.6 settings) was **promoted** to the live migration
``migrations/versions/202606240001_ads_v2_schema.py`` on 2026-06-24.

What remains here is the **deferred** ``ad_events`` per-event analytics table
(MASTER_PLAN §23 task 9.5.9 — "optional / last"). It is monthly RANGE-partitioned
like ``error_logs`` and never touches the counter hot path. Promote it the same way
when 9.5.9 is scheduled (see migrations/planned/README.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# PROMOTION: replace with the versions/ filename stem and the real head id.
revision: str = "ad_events_planned"
down_revision: str | None = None  # PROMOTION: set to `alembic heads` at implement time
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
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
        CREATE INDEX ix_ad_events_ad ON ad_events (advertisement_id, created_at);
        """
    )
    # PROMOTION TODO: pre-create the first N monthly partitions (see partitioning.py).


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ad_events;")
