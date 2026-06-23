"""ORM model for ``job_waiters`` (MASTER_PLAN 10.8, D-009)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class JobWaiter(Base):
    __tablename__ = "job_waiters"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Logical FK to jobs.id (jobs is partitioned).
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
