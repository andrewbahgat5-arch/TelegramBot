"""ORM model for ``message_templates`` (Sprint 13.8).

An admin-editable override for a user-facing message, keyed by ``(key, locale)``.
When a row exists it supersedes the shipped ``core.i18n`` default for that key; when
absent the default is used (the row is deleted on "reset to default").
"""

from __future__ import annotations

import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.models.base import Base


class MessageTemplate(Base):
    __tablename__ = "message_templates"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    locale: Mapped[str] = mapped_column(String(10), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
