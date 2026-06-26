"""User domain entity (MASTER_PLAN Component 9.4, Sprint 4).

``UserSnapshot`` is an immutable, framework-free view of a ``users`` row. It is the
object that crosses the service→bot boundary (attached to the handler context by
``AuthMiddleware``) and the value cached in Redis (D-014, Section 11.1 layer 3).

The conversions live here so the cache wire-format stays in one place:

* :meth:`from_row` builds a snapshot from an ORM row by attribute access only — it
  never imports the ORM model, so ``domain`` keeps its leaf position (Section 8).
* :meth:`to_cache_dict` / :meth:`from_cache_dict` round-trip through pure JSON
  primitives (timestamps as ISO-8601 strings), which is what ``CacheService``
  serialises with orjson.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from domain.enums import UserRole


@dataclass(frozen=True, slots=True)
class UserSnapshot:
    """Immutable snapshot of a ``users`` row (MASTER_PLAN 10.2)."""

    id: int
    telegram_id: int
    role: UserRole
    is_banned: bool
    is_premium: bool
    daily_download_count: int
    daily_download_count_reset_date: datetime.date
    total_downloads: int
    username: str | None = None
    first_name: str | None = None
    language: str | None = None
    premium_expires_at: datetime.datetime | None = None
    ban_reason: str | None = None
    last_activity_at: datetime.datetime | None = None
    created_at: datetime.datetime | None = None  # join date (admin User Info, Sprint 9.6)

    @classmethod
    def from_row(cls, row: Any) -> UserSnapshot:
        """Build a snapshot from a ``users`` ORM row (attribute access only)."""
        return cls(
            id=row.id,
            telegram_id=row.telegram_id,
            role=UserRole(row.role),
            is_banned=row.is_banned,
            is_premium=row.is_premium,
            daily_download_count=row.daily_download_count,
            daily_download_count_reset_date=row.daily_download_count_reset_date,
            total_downloads=row.total_downloads,
            username=row.username,
            first_name=row.first_name,
            language=row.language,
            premium_expires_at=row.premium_expires_at,
            ban_reason=row.ban_reason,
            last_activity_at=row.last_activity_at,
            created_at=getattr(row, "created_at", None),
        )

    def to_cache_dict(self) -> dict[str, Any]:
        """Render to JSON-safe primitives for the Redis user cache."""
        return {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "role": self.role.value,
            "is_banned": self.is_banned,
            "is_premium": self.is_premium,
            "daily_download_count": self.daily_download_count,
            "daily_download_count_reset_date": self.daily_download_count_reset_date.isoformat(),
            "total_downloads": self.total_downloads,
            "username": self.username,
            "first_name": self.first_name,
            "language": self.language,
            "premium_expires_at": _iso_or_none(self.premium_expires_at),
            "ban_reason": self.ban_reason,
            "last_activity_at": _iso_or_none(self.last_activity_at),
            "created_at": _iso_or_none(self.created_at),
        }

    @classmethod
    def from_cache_dict(cls, data: dict[str, Any]) -> UserSnapshot:
        """Rebuild a snapshot from its cached JSON form."""
        return cls(
            id=data["id"],
            telegram_id=data["telegram_id"],
            role=UserRole(data["role"]),
            is_banned=data["is_banned"],
            is_premium=data["is_premium"],
            daily_download_count=data["daily_download_count"],
            daily_download_count_reset_date=datetime.date.fromisoformat(
                data["daily_download_count_reset_date"]
            ),
            total_downloads=data["total_downloads"],
            username=data["username"],
            first_name=data["first_name"],
            language=data["language"],
            premium_expires_at=_dt_or_none(data["premium_expires_at"]),
            ban_reason=data["ban_reason"],
            last_activity_at=_dt_or_none(data["last_activity_at"]),
            created_at=_dt_or_none(data.get("created_at")),
        )


def _iso_or_none(value: datetime.datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _dt_or_none(value: str | None) -> datetime.datetime | None:
    return None if value is None else datetime.datetime.fromisoformat(value)
