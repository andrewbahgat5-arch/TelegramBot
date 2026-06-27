"""ORM model for ``ad_placements`` (Sprint 9.6, D-056).

Multi-placement: an advertisement may occupy several placements at once (one row per
placement), instead of the single ``advertisements.placement`` column. The scalar column
is retained and dual-read for one deprecation window (the D-043/D-044 pattern) — this
migration backfills one row per ad from it.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class AdPlacementLink(Base):
    __tablename__ = "ad_placements"

    advertisement_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("advertisements.id", ondelete="CASCADE"),
        primary_key=True,
    )
    placement: Mapped[str] = mapped_column(String(30), primary_key=True)
