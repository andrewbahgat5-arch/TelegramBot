"""Seed the admin-editable cookie pool policy (DESIGN_COOKIE_POOL.md §13).

The six values the Owner asked to be configurable — plus the related caps — live in the
``settings`` table rather than env or constants, so they are retunable from the admin
panel without a redeploy. ``CookiePolicyProvider`` reads them; an absent row falls back
to the ``CookiePolicy`` dataclass default, so this seed is convenience, not a dependency.

Revision ID: 2026071802
Revises: 2026071801
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2026071802"
down_revision: str | None = "2026071801"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (key, value, type, description)
_SETTINGS: tuple[tuple[str, str, str, str], ...] = (
    ("cookie_selection_strategy", "lru", "string", "Cookie pick order: lru|round_robin|weighted|sticky."),
    ("cookie_max_concurrent_leases", "1", "int", "Simultaneous runs allowed per cookie."),
    ("cookie_warning_threshold", "2", "int", "Consecutive auth failures before WARNING."),
    ("cookie_cooldown_threshold", "3", "int", "Consecutive auth failures before cooldown."),
    ("cookie_cooldown_seconds", "300", "int", "Base cooldown; triples each cycle."),
    ("cookie_cooldown_max_seconds", "3600", "int", "Cooldown ceiling."),
    ("cookie_max_cooldown_cycles", "3", "int", "Cooldown cycles before EXPIRED."),
    ("cookie_lease_ttl_seconds", "900", "int", "Lease expiry safety net (crashed worker)."),
    ("cookie_allow_affinity_break", "false", "bool", "Allow borrowing a cookie across egresses."),
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO settings (key, value, value_type, description) "
            "VALUES (:key, :value, :value_type, :description) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        [
            {"key": key, "value": value, "value_type": value_type, "description": description}
            for key, value, value_type, description in _SETTINGS
        ],
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM settings WHERE key = :key"),
        [{"key": key} for key, _, _, _ in _SETTINGS],
    )
