"""ORM model for ``users`` (MASTER_PLAN 10.2)."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Identity,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str | None] = mapped_column(String(10))
    role: Mapped[str] = mapped_column(String(20), nullable=False, server_default="user")
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    premium_expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    banned_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    ban_reason: Mapped[str | None] = mapped_column(String(500))
    daily_download_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    daily_download_count_reset_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    total_downloads: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_activity_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
