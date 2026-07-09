"""add buttons JSONB to message_templates

Revision ID: 2026070904
Revises: 2026070903
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "2026070904"
down_revision = "2026070903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message_templates", sa.Column("buttons", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("message_templates", "buttons")
