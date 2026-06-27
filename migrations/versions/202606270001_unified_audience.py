"""Sprint 9.6 — unified audience engine: audience_expressions + audience_rules (D-055).

Additive-first per §19.1. Creates the reusable ``audience_expressions`` (mode) +
``audience_rules`` (effect/dimension/value) tables and adds a nullable
``audience_expression_id`` FK to both ``advertisements`` and ``broadcasts`` so ads,
broadcasts, and future messaging features share one targeting model
(``DESIGN_9.6_unified_audience_wizard.md``, Option A).

Backfill (dual-read window, D-043/D-044 pattern): every advertisement that already has
``ad_audience_rules`` gets an equivalent expression (mode = its ``audience_mode``, rules
copied), and its ``audience_expression_id`` is pointed at that expression. The legacy
``ad_audience_rules`` table is left intact; the read path still uses it until the engine
is switched to dual-read in a later checkpoint. Broadcasts are not backfilled (legacy
broadcasts keep using ``target_role`` / ``target_language``).

Revision ID: 202606270001
Revises: 202606250002
Create Date: 2026-06-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202606270001"
down_revision: str | None = "202606250002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    """CREATE TABLE audience_expressions (
        id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        mode       VARCHAR(10) NOT NULL DEFAULT 'all',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );""",
    """CREATE TABLE audience_rules (
        id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        expression_id BIGINT NOT NULL REFERENCES audience_expressions (id) ON DELETE CASCADE,
        effect        VARCHAR(10) NOT NULL,
        dimension     VARCHAR(20) NOT NULL,
        value         VARCHAR(64) NOT NULL
    );""",
    "CREATE INDEX ix_audience_rules_expression ON audience_rules (expression_id);",
    "ALTER TABLE advertisements ADD COLUMN audience_expression_id BIGINT "
    "REFERENCES audience_expressions (id) ON DELETE SET NULL;",
    "ALTER TABLE broadcasts ADD COLUMN audience_expression_id BIGINT "
    "REFERENCES audience_expressions (id) ON DELETE SET NULL;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE broadcasts DROP COLUMN IF EXISTS audience_expression_id;",
    "ALTER TABLE advertisements DROP COLUMN IF EXISTS audience_expression_id;",
    "DROP TABLE IF EXISTS audience_rules;",
    "DROP TABLE IF EXISTS audience_expressions;",
)


def _backfill(bind) -> None:  # type: ignore[no-untyped-def]  # migrations are not type-checked
    """Copy each ad's ``ad_audience_rules`` into an equivalent shared expression.

    ``bind`` is the Alembic connection in ``upgrade()``; tests pass a sync Session via
    ``AsyncSession.run_sync`` to exercise this same logic against seeded data.
    """
    ad_ids = [
        row[0]
        for row in bind.execute(
            sa.text("SELECT DISTINCT advertisement_id FROM ad_audience_rules ORDER BY 1")
        ).all()
    ]
    for ad_id in ad_ids:
        mode = bind.execute(
            sa.text("SELECT audience_mode FROM advertisements WHERE id = :a"), {"a": ad_id}
        ).scalar_one()
        expr_id = bind.execute(
            sa.text("INSERT INTO audience_expressions (mode) VALUES (:m) RETURNING id"),
            {"m": mode},
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO audience_rules (expression_id, effect, dimension, value) "
                "SELECT :e, effect, dimension, value FROM ad_audience_rules "
                "WHERE advertisement_id = :a"
            ),
            {"e": expr_id, "a": ad_id},
        )
        bind.execute(
            sa.text("UPDATE advertisements SET audience_expression_id = :e WHERE id = :a"),
            {"e": expr_id, "a": ad_id},
        )


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)
    _backfill(op.get_bind())


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
