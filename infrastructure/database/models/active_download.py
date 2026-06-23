"""ORM model for ``active_downloads`` (MASTER_PLAN 10.7)."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class ActiveDownload(Base):
    __tablename__ = "active_downloads"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("media_metadata.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    quality: Mapped[str] = mapped_column(String(20), nullable=False)
    # Logical link to jobs.id only (jobs is partitioned; no FK action). D-009/10.14.
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
