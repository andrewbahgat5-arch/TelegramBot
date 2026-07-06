"""ORM model for ``rewards`` (Reward Engine, D-075).

Append-only grants: one row per reward granted to a user by some source (a
referral today; admin/promotions/future sources tomorrow). ``expires_at`` NULL is a
permanent reward. Consumed via the ``RewardService``, never referenced by source.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # A domain.rewards.RewardType value (validated at the service boundary).
    reward_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # Numeric magnitude; meaning is per-type (extra downloads, days, credits, level…).
    value: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Optional type-specific data (e.g. a quality code for UNLOCK_QUALITY).
    param: Mapped[str | None] = mapped_column(String(100))
    # Provenance (e.g. "referral", "admin"); free-form, never used for enforcement.
    source: Mapped[str] = mapped_column(String(40), nullable=False, server_default="")
    granted_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # NULL = permanent; otherwise the reward is inactive once now() passes it.
    expires_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
