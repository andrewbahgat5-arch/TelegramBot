"""ORM models for ``audience_expressions`` + ``audience_rules`` (Sprint 9.6, D-055).

A reusable, feature-agnostic audience expression: a ``mode`` (all/include/exclude) plus
zero or more rules (``effect`` / ``dimension`` / ``value``), referenced by a nullable
``audience_expression_id`` FK on ``advertisements`` and ``broadcasts`` so the *same*
targeting model serves ads, broadcasts, and future messaging features
(``DESIGN_9.6_unified_audience_wizard.md``, Option A).

The Sprint 9.5 ``ad_audience_rules`` table is retained and dual-read for one deprecation
window (the D-043/D-044 pattern); this migration backfills an equivalent expression for
every ad that already has rules.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class AudienceExpression(Base):
    __tablename__ = "audience_expressions"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="all")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AudienceRule(Base):
    __tablename__ = "audience_rules"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    expression_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("audience_expressions.id", ondelete="CASCADE"),
        nullable=False,
    )
    effect: Mapped[str] = mapped_column(String(10), nullable=False)  # include | exclude
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
