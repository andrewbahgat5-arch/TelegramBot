"""ORM model for ``ad_buttons`` (MASTER_PLAN Sprint 9.5, D-042)."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class AdButton(Base):
    __tablename__ = "ad_buttons"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    advertisement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    row: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
