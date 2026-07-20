"""ORM model for ``error_logs`` (MASTER_PLAN 10.12, monthly RANGE partitioned).

PK is composite ``(id, created_at)``.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_type: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[str | None] = mapped_column(Text)
    # --- observability (DESIGN_MONITORING.md) ---------------------------------
    # Classification: drives BOTH the Telegram-vs-dashboard routing and the split
    # between the dashboard's Errors and Logs views.
    severity: Mapped[str | None] = mapped_column(String(10))
    category: Mapped[str | None] = mapped_column(String(40))
    # Request context, denormalised because the dashboard filters on it constantly.
    platform: Mapped[str | None] = mapped_column(String(30))
    url: Mapped[str | None] = mapped_column(Text)
    url_host: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    # Open-ended extras (quality, format, stage, worker id, duration, cache hit).
    context: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=func.now(),
    )
