"""UserService (MASTER_PLAN Component 9.2, Task 4.1).

User registration, role management, ban administration, and lookups. Reads run
through the Redis user cache (D-014, Section 11.1 layer 3); every write to a
``users`` row invalidates that user's cache entry (Section 11.3). ``last_activity_at``
writes are debounced so the hot path does not write on every update (Section 9.2).

The service is framework-agnostic: it depends on ``UserRepositoryProtocol`` and
``CacheService`` only, never on the ORM model or aiogram types (Section 8). The bot
layer extracts identity primitives from the Telegram update and passes them in.
"""

from __future__ import annotations

import csv
import datetime
import io
import json
from dataclasses import dataclass, field
from typing import Any

from core.constants import LAST_ACTIVITY_DEBOUNCE_SECONDS
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from domain.protocols.repositories import UserRepositoryProtocol
from services.cache_service import CacheService

_log = get_logger("services.user_service")

# Subscriber export/import column order (SPRINT_13_PLAN §13.6).
_EXPORT_FIELDS: tuple[str, ...] = (
    "telegram_id",
    "username",
    "first_name",
    "language",
    "role",
    "is_premium",
    "is_banned",
    "bot_blocked",
    "total_downloads",
    "daily_download_count",
    "referred_by",
    "created_at",
    "last_activity_at",
)
_EXPORT_PAGE = 500


@dataclass(frozen=True, slots=True)
class UserStats:
    """Aggregate user counts for the admin ``/stats`` command (Task 8.2).

    The richer cohort fields (joined today / this week, active today, premium, staff)
    feed the panel Statistics screen. They default to ``0`` so existing callers that
    only set the core three keep working.
    """

    total_users: int
    banned_users: int
    total_downloads: int
    new_today: int = 0
    new_this_week: int = 0
    active_today: int = 0
    premium_users: int = 0
    staff_users: int = 0
    # Enhanced activity metrics (Sprint 13.4). Default 0 so callers that build a
    # UserStats directly (tests, legacy paths) keep working unchanged.
    active_24h: int = 0
    active_7d: int = 0
    active_30d: int = 0
    inactive_5d: int = 0
    inactive_7d: int = 0
    inactive_30d: int = 0
    active_current_hour: int = 0
    active_previous_hour: int = 0
    # User-health counts (Sprint 13.5).
    blocked_users: int = 0
    deleted_users: int = 0


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Outcome of a subscriber import (SPRINT_13_PLAN §13.6)."""

    created: int
    skipped: int
    failed: int
    errors: list[str] = field(default_factory=list)


class UserService:
    def __init__(
        self,
        repo: UserRepositoryProtocol[Any],
        cache: CacheService,
        *,
        owner_telegram_id: int,
        debounce_seconds: int = LAST_ACTIVITY_DEBOUNCE_SECONDS,
    ) -> None:
        self._repo = repo
        self._cache = cache
        self._owner_telegram_id = owner_telegram_id
        self._debounce = datetime.timedelta(seconds=debounce_seconds)

    async def get_or_create_user(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        language: str | None = None,
    ) -> UserSnapshot:
        """Resolve a Telegram user to a snapshot, creating the row on first contact.

        Cache-first (D-014): a hit returns without touching Postgres. On a miss the
        row is loaded (or created) and the cache is populated.
        """
        cached = await self._cache.get_user(telegram_id)
        if cached is not None:
            return UserSnapshot.from_cache_dict(cached)

        row = await self._repo.get_by_telegram_id(telegram_id)
        if row is None:
            role = UserRole.OWNER if telegram_id == self._owner_telegram_id else UserRole.USER
            row = await self._repo.create_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                language=language,
                role=role.value,
            )
            _log.info("user_created", user_id=row.id, role=role.value)

        snapshot = UserSnapshot.from_row(row)
        await self._cache.set_user(telegram_id, snapshot.to_cache_dict())
        return snapshot

    async def record_activity(self, snapshot: UserSnapshot) -> None:
        """Persist ``last_activity_at`` at most once per debounce window per user."""
        now = datetime.datetime.now(datetime.UTC)
        last = snapshot.last_activity_at
        if last is not None and (now - last) < self._debounce:
            return
        await self._repo.touch_last_activity(snapshot.telegram_id, now)
        await self._cache.delete_user(snapshot.telegram_id)

    async def find(self, telegram_id: int) -> UserSnapshot | None:
        """Look up a user without creating one (admin ``/userinfo``). Bypasses the cache."""
        row = await self._repo.get_by_telegram_id(telegram_id)
        return None if row is None else UserSnapshot.from_row(row)

    async def get_stats(self) -> UserStats:
        """Aggregate counts for admin stats (totals, today/week cohorts, premium, staff)."""
        now = datetime.datetime.now(datetime.UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - datetime.timedelta(days=7)
        return UserStats(
            total_users=await self._repo.count_all(),
            banned_users=await self._repo.count_banned(),
            total_downloads=await self._repo.sum_total_downloads(),
            new_today=await self._repo.count_created_since(today_start),
            new_this_week=await self._repo.count_created_since(week_ago),
            active_today=await self._repo.count_active_since(today_start),
            premium_users=await self._repo.count_premium(),
            staff_users=await self._repo.count_staff(),
            active_24h=await self._repo.count_active_in_hours(24),
            active_7d=await self._repo.count_active_in_hours(24 * 7),
            active_30d=await self._repo.count_active_in_hours(24 * 30),
            inactive_5d=await self._repo.count_inactive_days(5),
            inactive_7d=await self._repo.count_inactive_days(7),
            inactive_30d=await self._repo.count_inactive_days(30),
            active_current_hour=await self._repo.count_active_current_hour(),
            active_previous_hour=await self._repo.count_active_previous_hour(),
            blocked_users=await self._repo.count_blocked(),
            deleted_users=await self._repo.count_deleted(),
        )

    async def export_users(self, fmt: str = "csv") -> tuple[bytes, str]:
        """Serialize every user to CSV or JSON. Returns ``(file_bytes, filename)`` (13.6)."""
        rows = await self._collect_all_rows()
        date = datetime.datetime.now(datetime.UTC).date().isoformat()
        if fmt == "json":
            payload = {
                "exported_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "total_users": len(rows),
                "users": [_export_row(row) for row in rows],
            }
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            return data, f"subscribers_{date}.json"
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=_EXPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_export_csv_row(row))
        return buffer.getvalue().encode("utf-8"), f"subscribers_{date}.csv"

    async def import_users(self, data: list[dict[str, Any]]) -> ImportResult:
        """Bulk-create users from parsed rows. Create-only: never overwrite existing (13.6)."""
        created = skipped = failed = 0
        errors: list[str] = []
        for index, raw in enumerate(data):
            telegram_id = _parse_telegram_id(raw.get("telegram_id"))
            if telegram_id is None:
                failed += 1
                errors.append(f"row {index + 1}: invalid telegram_id {raw.get('telegram_id')!r}")
                continue
            if await self._repo.get_by_telegram_id(telegram_id) is not None:
                skipped += 1
                continue
            await self._repo.create_user(
                telegram_id=telegram_id,
                username=_clean_str(raw.get("username")),
                first_name=_clean_str(raw.get("first_name")),
                language=_clean_str(raw.get("language")),
                role=UserRole.USER.value,
            )
            await self._cache.delete_user(telegram_id)
            created += 1
        _log.info("users_imported", created=created, skipped=skipped, failed=failed)
        return ImportResult(created=created, skipped=skipped, failed=failed, errors=errors)

    async def _collect_all_rows(self) -> list[Any]:
        """Page through every user row for export (bounded page size)."""
        rows: list[Any] = []
        offset = 0
        while True:
            page = await self._repo.list_paginated(limit=_EXPORT_PAGE, offset=offset)
            rows.extend(page)
            if len(page) < _EXPORT_PAGE:
                return rows
            offset += len(page)

    async def list_users(self, *, limit: int = 30, offset: int = 0) -> list[UserSnapshot]:
        """A page of users for the owner ``/users`` listing (Task 8.2 follow-up #19)."""
        rows = await self._repo.list_paginated(limit=limit, offset=offset)
        return [UserSnapshot.from_row(row) for row in rows]

    async def set_role(self, telegram_id: int, role: UserRole) -> UserSnapshot | None:
        """Assign ``role`` to a user. Returns the updated snapshot, or None if absent."""
        return await self._mutate(
            telegram_id, lambda row: _apply(row, role=role.value), event="user_role_changed"
        )

    async def set_language(self, telegram_id: int, language: str) -> UserSnapshot | None:
        """Persist a user's explicitly chosen UI language (Sprint 11.5).

        Callers validate ``language`` against ``core.i18n.list_enabled_locales()``
        before calling this — this method just writes whatever it's given.
        """
        return await self._mutate(
            telegram_id, lambda row: _apply(row, language=language), event="user_language_changed"
        )

    async def ban(self, telegram_id: int, reason: str | None = None) -> UserSnapshot | None:
        """Ban a user, recording the audit fields (``banned_at``, ``ban_reason``)."""
        now = datetime.datetime.now(datetime.UTC)
        return await self._mutate(
            telegram_id,
            lambda row: _apply(row, is_banned=True, banned_at=now, ban_reason=reason),
            event="user_banned",
        )

    async def unban(self, telegram_id: int) -> UserSnapshot | None:
        """Lift a ban and clear the ban fields (``banned_at``, ``ban_reason``) → NULL.

        An unbanned user has no active ban, so the reason/timestamp are cleared rather
        than retained (Owner directive 2026-06-26, D-054): a non-banned user must never
        show a stale ban reason. Durable ban history lives in the audit log (V3).
        """
        return await self._mutate(
            telegram_id,
            lambda row: _apply(row, is_banned=False, banned_at=None, ban_reason=None),
            event="user_unbanned",
        )

    async def set_premium(
        self,
        telegram_id: int,
        *,
        is_premium: bool,
        expires_at: datetime.datetime | None = None,
    ) -> UserSnapshot | None:
        """Toggle a user's premium flag (and ``premium_expires_at``). Returns the snapshot.

        A V1 data write only: it sets the existing ``users`` columns. Premium *enforcement*
        (limits / cooldowns / queue priority) stays V2, but the audience/ads layer keys off
        ``is_premium`` immediately (the PLAN dimension), so a toggle changes which campaigns
        a user matches. Clearing premium also clears ``premium_expires_at``.
        """
        return await self._mutate(
            telegram_id,
            lambda row: _apply(
                row,
                is_premium=is_premium,
                premium_expires_at=expires_at if is_premium else None,
            ),
            event="user_premium_changed",
        )

    async def _mutate(self, telegram_id: int, apply: Any, *, event: str) -> UserSnapshot | None:
        row = await self._repo.get_by_telegram_id(telegram_id)
        if row is None:
            return None
        apply(row)
        await self._repo.add(row)
        await self._cache.delete_user(telegram_id)
        _log.info(event, user_id=row.id)
        return UserSnapshot.from_row(row)


def _apply(row: Any, **fields: Any) -> None:
    for name, value in fields.items():
        setattr(row, name, value)


def _iso_or_none(value: datetime.datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _export_row(row: Any) -> dict[str, Any]:
    """Native-typed export dict (booleans/ints/None preserved) for JSON output."""
    return {
        "telegram_id": row.telegram_id,
        "username": row.username,
        "first_name": row.first_name,
        "language": row.language,
        "role": row.role,
        "is_premium": bool(row.is_premium),
        "is_banned": bool(row.is_banned),
        "bot_blocked": bool(getattr(row, "bot_blocked", False)),
        "total_downloads": row.total_downloads,
        "daily_download_count": row.daily_download_count,
        "referred_by": getattr(row, "referred_by_id", None),
        "created_at": _iso_or_none(getattr(row, "created_at", None)),
        "last_activity_at": _iso_or_none(getattr(row, "last_activity_at", None)),
    }


def _export_csv_row(row: Any) -> dict[str, str]:
    """String-ified export dict for CSV (bools lowercased, None → empty string)."""
    out: dict[str, str] = {}
    for key, value in _export_row(row).items():
        if value is None:
            out[key] = ""
        elif isinstance(value, bool):
            out[key] = "true" if value else "false"
        else:
            out[key] = str(value)
    return out


def _parse_telegram_id(value: Any) -> int | None:
    """Coerce an imported telegram_id to int, or None if missing/invalid."""
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_str(value: Any) -> str | None:
    """Normalize an optional imported string field (blank/empty → None)."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
