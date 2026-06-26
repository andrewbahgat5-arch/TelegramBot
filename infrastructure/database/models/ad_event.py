"""ORM model for ``ad_events`` (MASTER_PLAN 10.16, Sprint 9.5.9, D-045).

Per-event ad analytics, monthly RANGE-partitioned by ``created_at`` like
``error_logs``. PK is composite ``(id, created_at)``. Rows are written **off** the
delivery hot path (D-052); the per-ad/per-button counters on ``advertisements`` /
``ad_buttons`` remain the source of truth. No foreign keys (matches the locked
skeleton): the analytics write stays cheap and never contends with ad CRUD, and a
deleted ad's events age out with their partition.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class AdEvent(Base):
    __tablename__ = "ad_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    advertisement_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    event_type: Mapped[str] = mapped_column(String(12), nullable=False)
    placement: Mapped[str | None] = mapped_column(String(30))
    button_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=func.now(),
    )
