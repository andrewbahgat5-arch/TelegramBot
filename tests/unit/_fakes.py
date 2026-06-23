"""In-memory fakes for Sprint 4 unit tests (not a test module).

These let the services run without Postgres or Redis while still exercising the
real ``CacheService`` / ``SettingsService`` logic (key building, type casting). The
fakes satisfy the same protocols the production code depends on.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import Settings
from core.uuid7 import uuid7_str
from services.cache_service import CacheService

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def load_settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


# --- Redis fakes ----------------------------------------------------------
class FakeCache:
    """In-memory ``CacheProtocol``. TTLs are accepted but ignored."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, *, ttl: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)

    async def incr_with_ttl(self, key: str, *, ttl: int) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value


class FakeLock:
    """In-memory ``LockProtocol`` with token-tagged release."""

    def __init__(self) -> None:
        self.held: dict[str, str] = {}

    async def acquire(self, key: str, *, ttl: int) -> str | None:
        if key in self.held:
            return None
        token = uuid7_str()
        self.held[key] = token
        return token

    async def release(self, key: str, token: str) -> bool:
        if self.held.get(key) == token:
            del self.held[key]
            return True
        return False


def make_cache_service() -> tuple[CacheService, FakeCache]:
    cache = FakeCache()
    return CacheService(cache, FakeLock(), load_settings()), cache


# --- User row + repository fakes ------------------------------------------
def _today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


@dataclass
class FakeUser:
    id: int
    telegram_id: int
    role: str = "user"
    is_banned: bool = False
    is_premium: bool = False
    premium_expires_at: datetime.datetime | None = None
    banned_at: datetime.datetime | None = None
    ban_reason: str | None = None
    daily_download_count: int = 0
    daily_download_count_reset_date: datetime.date = field(default_factory=_today)
    total_downloads: int = 0
    username: str | None = None
    first_name: str | None = None
    language: str | None = None
    last_activity_at: datetime.datetime | None = None
    updated_at: datetime.datetime | None = None


class FakeUserRepo:
    """In-memory ``UserRepositoryProtocol[FakeUser]``."""

    def __init__(self) -> None:
        self.by_tid: dict[int, FakeUser] = {}
        self._next_id = 1
        self.touch_calls: list[tuple[int, datetime.datetime]] = []

    async def add(self, entity: FakeUser) -> FakeUser:
        self.by_tid[entity.telegram_id] = entity
        return entity

    async def get_by_id(self, id_: Any) -> FakeUser | None:
        return next((u for u in self.by_tid.values() if u.id == id_), None)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[FakeUser]:
        return list(self.by_tid.values())[offset : offset + limit]

    async def delete(self, entity: FakeUser) -> None:
        self.by_tid.pop(entity.telegram_id, None)

    async def get_by_telegram_id(self, telegram_id: int) -> FakeUser | None:
        return self.by_tid.get(telegram_id)

    async def create_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        language: str | None,
        role: str,
    ) -> FakeUser:
        user = FakeUser(
            id=self._next_id,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            language=language,
            role=role,
        )
        self._next_id += 1
        self.by_tid[telegram_id] = user
        return user

    async def touch_last_activity(self, telegram_id: int, when: datetime.datetime) -> None:
        self.touch_calls.append((telegram_id, when))
        user = self.by_tid.get(telegram_id)
        if user is not None:
            user.last_activity_at = when

    async def reset_daily_download_count_if_needed(
        self, user: FakeUser, *, today: datetime.date | None = None
    ) -> FakeUser:
        current = today or _today()
        if user.daily_download_count_reset_date < current:
            user.daily_download_count = 0
            user.daily_download_count_reset_date = current
        return user


# --- Settings store fake --------------------------------------------------
@dataclass
class FakeSettingRow:
    value: str
    value_type: str


class FakeSettingsStore:
    """In-memory ``SettingsStoreProtocol``."""

    def __init__(self, data: dict[str, tuple[str, str]]) -> None:
        self._data = dict(data)

    async def get_by_key(self, key: str) -> FakeSettingRow | None:
        if key not in self._data:
            return None
        value, value_type = self._data[key]
        return FakeSettingRow(value, value_type)

    async def upsert(
        self, key: str, value: str, *, updated_by: int | None = None
    ) -> FakeSettingRow:
        value_type = self._data.get(key, (value, "string"))[1]
        self._data[key] = (value, value_type)
        return FakeSettingRow(value, value_type)


DEFAULT_RATE_SETTINGS: dict[str, tuple[str, str]] = {
    "rate_limit_messages_per_minute": ("30", "int"),
    "maintenance_mode": ("false", "bool"),
    "free_daily_limit": ("10", "int"),
    "premium_daily_limit": ("100", "int"),
    "download_cooldown_seconds": ("30", "int"),
    "premium_download_cooldown_seconds": ("5", "int"),
}
