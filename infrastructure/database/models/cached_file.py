"""ORM model for ``cached_files`` (MASTER_PLAN 10.4)."""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class CachedFile(Base):
    __tablename__ = "cached_files"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    media_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("media_metadata.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    quality: Mapped[str] = mapped_column(String(20), nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_unique_file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int | None] = mapped_column(BigInteger)
    usage_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_used_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
