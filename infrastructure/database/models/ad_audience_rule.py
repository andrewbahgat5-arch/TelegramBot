"""ORM model for ``ad_audience_rules`` (MASTER_PLAN Sprint 9.5, D-043)."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Identity, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class AdAudienceRule(Base):
    __tablename__ = "ad_audience_rules"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    advertisement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("advertisements.id", ondelete="CASCADE"), nullable=False
    )
    effect: Mapped[str] = mapped_column(String(10), nullable=False)  # include | exclude
    dimension: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
