"""YouTube cookie pool — ``youtube_cookies`` + ``youtube_cookie_events``.

DESIGN_COOKIE_POOL.md §6. Metadata, health and statistics only; cookie material stays
on disk (see ``CookieStoreProtocol``) so rotation write-back is a cheap local write and
live Google sessions never enter a database backup.

Two failure counters by design: ``auth_failures`` drives health, ``total_other_failures``
is statistics only. That separation is what structurally prevents a route failure (a
bot-check wall, a proxy outage) from ever degrading a cookie.

Revision ID: 2026071801
Revises: 2026070906
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "2026071801"
down_revision: str | None = "2026070906"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS youtube_cookies (
        id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        label                VARCHAR(40)  NOT NULL UNIQUE,
        status               VARCHAR(20)  NOT NULL DEFAULT 'healthy',
        cooldown_until       TIMESTAMPTZ,
        egress_id            VARCHAR(40),
        file_version         INTEGER      NOT NULL DEFAULT 1,
        content_hash         VARCHAR(64)  NOT NULL DEFAULT '',
        auth_failures        INTEGER      NOT NULL DEFAULT 0,
        cooldown_cycles      INTEGER      NOT NULL DEFAULT 0,
        total_uses           BIGINT       NOT NULL DEFAULT 0,
        total_success        BIGINT       NOT NULL DEFAULT 0,
        total_auth_failures  BIGINT       NOT NULL DEFAULT 0,
        total_other_failures BIGINT       NOT NULL DEFAULT 0,
        last_used_at         TIMESTAMPTZ,
        last_success_at      TIMESTAMPTZ,
        last_failure_at      TIMESTAMPTZ,
        last_failure_reason  TEXT,
        notes                TEXT,
        created_by           BIGINT REFERENCES users(id) ON DELETE SET NULL,
        created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
        updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
    );
    """,
    # The selection hot path: "selectable cookies for this egress, least recently used".
    """
    CREATE INDEX IF NOT EXISTS ix_youtube_cookies_selection
        ON youtube_cookies (status, egress_id, last_used_at NULLS FIRST);
    """,
    """
    CREATE TABLE IF NOT EXISTS youtube_cookie_events (
        id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        cookie_id     BIGINT NOT NULL REFERENCES youtube_cookies(id) ON DELETE CASCADE,
        event         VARCHAR(40) NOT NULL,
        from_status   VARCHAR(20),
        to_status     VARCHAR(20),
        reason        TEXT,
        egress_id     VARCHAR(40),
        actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_youtube_cookie_events_cookie
        ON youtube_cookie_events (cookie_id, created_at DESC);
    """,
)

_DOWNGRADE_DDL: tuple[str, ...] = (
    "DROP TABLE IF EXISTS youtube_cookie_events;",
    "DROP TABLE IF EXISTS youtube_cookies;",
)


def upgrade() -> None:
    for statement in _UPGRADE_DDL:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE_DDL:
        op.execute(statement)
