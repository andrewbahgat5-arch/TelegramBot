"""ORM models for the YouTube cookie pool (DESIGN_COOKIE_POOL.md §6).

``youtube_cookies`` holds identity, health and statistics — never the cookie material
itself, which lives on disk behind ``CookieStoreProtocol`` so rotation write-back stays a
cheap local write and live Google sessions stay out of database backups.

``youtube_cookie_events`` is the append-only audit trail: every state change, replacement
and affinity pin, with the acting admin where there was one.
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class YoutubeCookie(Base):
    __tablename__ = "youtube_cookies"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    #: Admin-facing name shown in notifications and the panel ("yt-03").
    label: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="healthy")
    #: Orthogonal to status: a benched-but-otherwise-healthy cookie (§7).
    cooldown_until: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    #: Affinity — the egress endpoint id this session is pinned to. NULL until first use.
    egress_id: Mapped[str | None] = mapped_column(String(40))
    file_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")

    #: Consecutive AUTH failures only — route/content failures never touch this (§7).
    auth_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cooldown_cycles: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    total_uses: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_success: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_auth_failures: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    #: Route/content/unclassified failures — statistics only, never health.
    total_other_failures: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )

    last_used_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_reason: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class YoutubeCookieEvent(Base):
    __tablename__ = "youtube_cookie_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    cookie_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("youtube_cookies.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    egress_id: Mapped[str | None] = mapped_column(String(40))
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
