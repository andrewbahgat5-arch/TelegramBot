"""ORM model for ``media_metadata`` (MASTER_PLAN 10.3)."""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class MediaMetadata(Base):
    __tablename__ = "media_metadata"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    video_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
