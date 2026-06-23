"""ORM model for ``advertisements`` (MASTER_PLAN 10.10)."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class Advertisement(Base):
    __tablename__ = "advertisements"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="text")
    content_text: Mapped[str | None] = mapped_column(Text)
    content_media_file_id: Mapped[str | None] = mapped_column(String(255))
    button_text: Mapped[str | None] = mapped_column(String(100))
    button_url: Mapped[str | None] = mapped_column(Text)
    target_role: Mapped[str | None] = mapped_column(String(20))
    show_every_n_downloads: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
