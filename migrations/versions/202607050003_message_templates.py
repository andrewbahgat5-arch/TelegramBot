"""Sprint 13.8 — admin-editable message templates.

Additive-first per §19.1. One row per ``(key, locale)`` overrides the shipped
``core.i18n`` default for that key; deleting the row reverts to the default.

Revision ID: 202607050003
Revises: 202607050002
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607050003"
down_revision: str | None = "202607050002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UPGRADE_DDL: tuple[str, ...] = (
    """CREATE TABLE message_templates (
        key        VARCHAR(100) NOT NULL,
        locale     VARCHAR(10)  NOT NULL,
        content    TEXT         NOT NULL,
        is_custom  BOOLEAN      NOT NULL DEFAULT TRUE,
        updated_by BIGINT       REFERENCES users (id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
        PRIMARY KEY (key, locale)
    );""",
)

_DOWNGRADE_DDL: tuple[str, ...] = ("DROP TABLE IF EXISTS message_templates;",)


def upgrade() -> None:
    for ddl in _UPGRADE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in _DOWNGRADE_DDL:
        op.execute(ddl)
