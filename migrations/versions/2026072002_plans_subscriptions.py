"""V2.1: plans + subscriptions tables (VERSION_2_MASTER_PLAN §6.1/§6.2, §15 Step 1).

Additive only — the subscription foundation in shadow mode. ``users.is_premium`` is
untouched and stays authoritative until the V2.2 cutover; rollback for the whole sprint
is dropping these two tables (zero behavior to revert). Enums are stored as ``VARCHAR``
(codebase convention — no PG ENUM types; values are enforced app-side by the
``SubscriptionStatus``/``SubscriptionSource`` StrEnums). Seeding of the ``free``/``premium``
plan rows is a separate data migration (``2026072003``).

Revision ID: 2026072002
Revises: 2026072001
Create Date: 2026-07-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026072002"
down_revision: str | None = "2026072001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UPGRADE: tuple[str, ...] = (
    """
    CREATE TABLE plans (
        id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        code         VARCHAR(50) NOT NULL UNIQUE,
        name         VARCHAR(100) NOT NULL,
        is_active    BOOLEAN NOT NULL DEFAULT true,
        sort_order   INTEGER NOT NULL DEFAULT 0,
        entitlements JSONB NOT NULL,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE subscriptions (
        id                  UUID PRIMARY KEY,
        user_id             BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        plan_id             BIGINT NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
        status              VARCHAR(20) NOT NULL,
        source              VARCHAR(20) NOT NULL,
        starts_at           TIMESTAMPTZ NOT NULL,
        expires_at          TIMESTAMPTZ NOT NULL,
        notified_milestones SMALLINT NOT NULL DEFAULT 0,
        granted_by          BIGINT REFERENCES users(id) ON DELETE SET NULL,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    # One active subscription per user — the DB-level guarantee for V2-D-003.
    "CREATE UNIQUE INDEX ux_subscriptions_one_active "
    "ON subscriptions (user_id) WHERE status = 'active';",
    # Expiry scan support for the V2.2 notifier and the subscriptions_active gauge.
    "CREATE INDEX ix_subscriptions_expiring "
    "ON subscriptions (expires_at) WHERE status = 'active';",
)

_DOWNGRADE: tuple[str, ...] = (
    "DROP TABLE IF EXISTS subscriptions;",
    "DROP TABLE IF EXISTS plans;",
)


def upgrade() -> None:
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _DOWNGRADE:
        op.execute(stmt)
