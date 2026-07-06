"""Reward Engine (D-075) — generic ``rewards`` table; retire ``referral_bonus_downloads``.

Refactors the referral reward from a hard-coded ``users.referral_bonus_downloads``
counter into a generic, open-for-extension reward model:

* ``rewards`` — one row per granted reward (``reward_type``, ``value``, optional
  ``param``, ``source``, ``granted_at``, nullable ``expires_at``). NULL expiry =
  permanent. Indexed by ``(user_id, reward_type)`` for the active-value lookup.
* **Backfill:** each user's existing ``referral_bonus_downloads`` (> 0) becomes a
  permanent ``daily_download_bonus`` reward (``source='referral_legacy'``), so
  existing bonuses are preserved.
* **Drop** ``users.referral_bonus_downloads`` — the download-limit logic now consumes
  active rewards, so the column is gone (single source of truth).

Additive-forward per §19.1 (the column drop is the intended forward change); the
downgrade re-creates the column and rebuilds it from the active daily-download rewards.

Revision ID: 202607060001
Revises: 202607050003
Create Date: 2026-07-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607060001"
down_revision: str | None = "202607050003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    """CREATE TABLE rewards (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        user_id     BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
        reward_type VARCHAR(40) NOT NULL,
        value       INTEGER NOT NULL DEFAULT 0,
        param       VARCHAR(100),
        source      VARCHAR(40) NOT NULL DEFAULT '',
        granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at  TIMESTAMPTZ
    );""",
    "CREATE INDEX ix_rewards_user_type ON rewards (user_id, reward_type);",
    # Preserve existing referral bonuses as permanent daily-download rewards.
    """INSERT INTO rewards (user_id, reward_type, value, source, granted_at)
       SELECT id, 'daily_download_bonus', referral_bonus_downloads, 'referral_legacy', now()
       FROM users
       WHERE referral_bonus_downloads > 0;""",
    "ALTER TABLE users DROP COLUMN referral_bonus_downloads;",
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "ALTER TABLE users ADD COLUMN referral_bonus_downloads INTEGER NOT NULL DEFAULT 0;",
    # Rebuild the column from the active daily-download rewards.
    """UPDATE users u SET referral_bonus_downloads = COALESCE((
        SELECT SUM(r.value) FROM rewards r
        WHERE r.user_id = u.id
          AND r.reward_type = 'daily_download_bonus'
          AND (r.expires_at IS NULL OR r.expires_at > now())
    ), 0);""",
    "DROP TABLE IF EXISTS rewards;",
)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
