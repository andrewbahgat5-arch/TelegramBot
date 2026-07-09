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
    # Language-first ad creation: the admin picks English/Arabic before composing, so each
    # language has its own campaigns (listing groups by this). NULL = untargeted (legacy ads
    # created before this field, or a deliberately language-agnostic ad).
    target_language: Mapped[str | None] = mapped_column(String(10))
    # Ads v2 (Sprint 9.5): placement, delivery mode, copy-mode source, rich text, audience.
    placement: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="post_download"
    )
    delivery_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="fields")
    storage_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    storage_message_id: Mapped[int | None] = mapped_column(BigInteger)
    parse_mode: Mapped[str | None] = mapped_column(String(10))
    audience_mode: Mapped[str] = mapped_column(String(10), nullable=False, server_default="all")
    # Unified audience engine (Sprint 9.6, D-055): when set, targeting is read from this
    # shared expression; NULL = legacy ad_audience_rules / target_role (dual-read window).
    audience_expression_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("audience_expressions.id", ondelete="SET NULL")
    )
    # Internal admin-only metadata (Sprint 9.6, D-058): NEVER shown to end users / on any
    # delivery path — for managing campaigns at scale.
    internal_name: Mapped[str | None] = mapped_column(String(120))
    internal_notes: Mapped[str | None] = mapped_column(Text)
    show_every_n_downloads: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    impressions: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Scheduling (Sprint 9.5.10): NULL = eligible immediately. Set → not selected for any
    # placement until now ≥ this (a "starts showing at" gate, checked at selection time).
    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    # Fair-rotation cursor (UX sprint #10): the instant this ad was last delivered. Among
    # equal-priority ads that are due for the same download, selection prefers the one shown
    # longest ago (least-recently-shown), so they share exposure evenly. NULL = never shown,
    # which sorts first. Stamped on each successful impression.
    last_shown_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
