"""ORM model for ``broadcasts`` (MASTER_PLAN 10.9)."""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_language: Mapped[str | None] = mapped_column(String(10))
    target_role: Mapped[str | None] = mapped_column(String(20))
    # Ads v2 (Sprint 9.5): a broadcast may deliver a stored ad via copyMessage instead of
    # plain text. NULL = plain-text broadcast (Sprint 8 behavior).
    advertisement_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("advertisements.id", ondelete="SET NULL")
    )
    # Unified audience engine (Sprint 9.6, D-055): when set, the broadcast audience is the
    # shared expression; NULL = legacy target_role/target_language (dual-read window).
    audience_expression_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audience_expressions.id", ondelete="SET NULL")
    )
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_sent: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    # Scheduling (Sprint 9.5.10): NULL = send as soon as the worker polls (immediate,
    # Sprint 8 behavior). Set → the BroadcastWorker's due-poller skips it until now ≥ this.
    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
