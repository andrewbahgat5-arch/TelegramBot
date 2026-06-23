"""ORM model for ``jobs`` (MASTER_PLAN 10.6, monthly RANGE partitioned).

PK is composite ``(id, created_at)``; ``id`` is an application-generated UUIDv7
(D-013), so there is no database-side default.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    media_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("media_metadata.id", ondelete="RESTRICT"),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    quality: Mapped[str] = mapped_column(String(20), nullable=False)
    worker_kind: Mapped[str] = mapped_column(String(30), nullable=False, server_default="download")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1000")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="created")
    error_message: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
