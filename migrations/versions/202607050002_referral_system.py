"""Sprint 13.7 — referral system: user columns, ``referrals`` table, settings.

Additive-first per §19.1.

* ``users.referred_by_id`` (self-FK, SET NULL), ``users.referral_code`` (unique),
  ``users.referral_bonus_downloads`` (permanent bonus that stacks on the daily limit).
* ``referrals`` — one row per successful referral; ``referred_id`` unique so a user is
  referred at most once.
* Seeds ``referral_enabled`` (bool, default true) and ``referral_reward_downloads``
  (int, default 5) into the settings key set (ON CONFLICT DO NOTHING, idempotent).

Revision ID: 202607050002
Revises: 202607050001
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607050002"
down_revision: str | None = "202607050001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN referred_by_id BIGINT REFERENCES users (id) ON DELETE SET NULL;",
    "ALTER TABLE users ADD COLUMN referral_code VARCHAR(20);",
    "ALTER TABLE users ADD COLUMN referral_bonus_downloads INTEGER NOT NULL DEFAULT 0;",
    "CREATE UNIQUE INDEX ix_users_referral_code ON users (referral_code);",
    """CREATE TABLE referrals (
        id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        referrer_id    BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        referred_id    BIGINT NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
        reward_granted BOOLEAN NOT NULL DEFAULT FALSE,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );""",
    "CREATE INDEX ix_referrals_referrer_id ON referrals (referrer_id);",
    "CREATE INDEX ix_referrals_created_at ON referrals (created_at);",
)

_SEED_SETTINGS: tuple[tuple[str, str, str, str], ...] = (
    ("referral_enabled", "true", "bool", "Referral system master switch."),
    ("referral_reward_downloads", "5", "int", "Bonus downloads per successful referral."),
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP TABLE IF EXISTS referrals;",
    "DROP INDEX IF EXISTS ix_users_referral_code;",
    "ALTER TABLE users DROP COLUMN IF EXISTS referral_bonus_downloads;",
    "ALTER TABLE users DROP COLUMN IF EXISTS referral_code;",
    "ALTER TABLE users DROP COLUMN IF EXISTS referred_by_id;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)
    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, :value, :value_type, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        [
            {"key": k, "value": v, "value_type": vt, "description": d}
            for (k, v, vt, d) in _SEED_SETTINGS
        ],
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM settings WHERE key = ANY(:keys)"),
        {"keys": [k for (k, _v, _vt, _d) in _SEED_SETTINGS]},
    )
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
