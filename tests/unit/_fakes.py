"""In-memory fakes for Sprint 4-5 unit tests (not a test module).

These let the services run without Postgres or Redis while still exercising the
real ``CacheService`` / ``SettingsService`` logic (key building, type casting). The
fakes satisfy the same protocols the production code depends on.
"""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import Settings
from core.uuid7 import uuid7_str
from domain.entities.media import DownloadedFile, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.protocols.downloader import Capability, ProviderHealth
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

    async def increment_download_counters(
        self, user_id: int, *, today: datetime.date | None = None
    ) -> None:
        current = today or _today()
        user = next((u for u in self.by_tid.values() if u.id == user_id), None)
        if user is None:
            return
        user.total_downloads += 1
        if user.daily_download_count_reset_date == current:
            user.daily_download_count += 1
        else:
            user.daily_download_count = 1
            user.daily_download_count_reset_date = current

    async def count_all(self) -> int:
        return len(self.by_tid)

    async def count_banned(self) -> int:
        return sum(1 for u in self.by_tid.values() if u.is_banned)

    async def sum_total_downloads(self) -> int:
        return sum(u.total_downloads for u in self.by_tid.values())

    def _audience(self, role: str | None, language: str | None) -> list[FakeUser]:
        users = [u for u in self.by_tid.values() if not u.is_banned]
        if role is not None:
            users = [u for u in users if u.role == role]
        else:  # untargeted broadcast excludes Owner/Moderator (item #14)
            users = [u for u in users if u.role not in ("owner", "moderator")]
        if language is not None:
            users = [u for u in users if u.language == language]
        return sorted(users, key=lambda u: u.id)

    async def count_for_broadcast(self, *, role: str | None, language: str | None) -> int:
        return len(self._audience(role, language))

    async def page_for_broadcast(
        self, *, after_id: int, limit: int, role: str | None, language: str | None
    ) -> Sequence[FakeUser]:
        return [u for u in self._audience(role, language) if u.id > after_id][:limit]


# --- Settings store fake --------------------------------------------------
@dataclass
class FakeSettingRow:
    value: str
    value_type: str
    key: str = ""


class FakeSettingsStore:
    """In-memory ``SettingsStoreProtocol``."""

    def __init__(self, data: dict[str, tuple[str, str]]) -> None:
        self._data = dict(data)

    async def get_by_key(self, key: str) -> FakeSettingRow | None:
        if key not in self._data:
            return None
        value, value_type = self._data[key]
        return FakeSettingRow(value, value_type, key)

    async def upsert(
        self, key: str, value: str, *, updated_by: int | None = None
    ) -> FakeSettingRow:
        value_type = self._data.get(key, (value, "string"))[1]
        self._data[key] = (value, value_type)
        return FakeSettingRow(value, value_type, key)

    async def list_all(self) -> Sequence[FakeSettingRow]:
        return [FakeSettingRow(v, t, k) for k, (v, t) in sorted(self._data.items())]


DEFAULT_RATE_SETTINGS: dict[str, tuple[str, str]] = {
    "rate_limit_messages_per_minute": ("30", "int"),
    "maintenance_mode": ("false", "bool"),
    "free_daily_limit": ("10", "int"),
    "premium_daily_limit": ("100", "int"),
    "download_cooldown_seconds": ("30", "int"),
    "premium_download_cooldown_seconds": ("5", "int"),
}


# --- Downloader fakes (Sprint 5) ------------------------------------------
class FakeProvider:
    """A ``DownloaderProtocol`` whose outcomes are scripted by the test."""

    def __init__(
        self,
        name: str,
        *,
        priority: int = 100,
        platforms: set[str] | None = None,
        result: MediaInfo | None = None,
        error: Exception | None = None,
        health: ProviderHealth = ProviderHealth.OK,
    ) -> None:
        self.name = name
        self.priority = priority
        self.supported_platforms = platforms if platforms is not None else {"*"}
        self.capabilities = {Capability.VIDEO}
        self._result = result
        self._error = error
        self._health = health
        self.calls = 0

    async def extract_info(self, url: str) -> MediaInfo:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._result or MediaInfo(
            platform="generic", video_id="vid", title="T", source_url=url
        )

    async def download(
        self, media: MediaInfo, format_: MediaFormat, quality: Quality, dest: Path
    ) -> DownloadedFile:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return DownloadedFile(path=dest, size_bytes=1, format=format_, quality=quality)

    async def health_check(self) -> ProviderHealth:
        return self._health


class FakeProviderSettings:
    """An in-memory ``ProviderSettingsProtocol`` (Section 12.6.7)."""

    def __init__(
        self,
        *,
        enabled: dict[str, bool] | None = None,
        overrides: dict[str, int] | None = None,
        failover: bool = True,
        cooldown: int = 60,
        threshold: int = 3,
    ) -> None:
        self._enabled = enabled if enabled is not None else {}
        self._overrides = overrides or {}
        self._failover = failover
        self._cooldown = cooldown
        self._threshold = threshold

    async def providers_enabled(self) -> dict[str, bool]:
        return self._enabled

    async def priority_overrides(self) -> dict[str, int]:
        return self._overrides

    async def failover_enabled(self) -> bool:
        return self._failover

    async def cooldown_seconds(self) -> int:
        return self._cooldown

    async def failure_threshold(self) -> int:
        return self._threshold


@dataclass
class FakeMediaRow:
    id: int
    platform: str
    video_id: str
    title: str
    source_url: str
    duration: int | None = None
    thumbnail_url: str | None = None
    metadata_json: dict[str, Any] | None = None


class FakeMediaRepo:
    """In-memory ``MediaRepositoryProtocol[FakeMediaRow]``."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[str, str], FakeMediaRow] = {}
        self.by_id: dict[int, FakeMediaRow] = {}
        self._next_id = 1
        self.upserts = 0

    async def add(self, entity: FakeMediaRow) -> FakeMediaRow:
        self.by_id[entity.id] = entity
        self.by_key[(entity.platform, entity.video_id)] = entity
        return entity

    async def get_by_id(self, id_: Any) -> FakeMediaRow | None:
        return self.by_id.get(id_)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[FakeMediaRow]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: FakeMediaRow) -> None:
        self.by_id.pop(entity.id, None)
        self.by_key.pop((entity.platform, entity.video_id), None)

    async def get_by_platform_video(self, platform: str, video_id: str) -> FakeMediaRow | None:
        return self.by_key.get((platform, video_id))

    async def upsert_metadata(
        self,
        *,
        platform: str,
        video_id: str,
        title: str,
        source_url: str,
        duration: int | None = None,
        thumbnail_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> FakeMediaRow:
        self.upserts += 1
        existing = self.by_key.get((platform, video_id))
        if existing is None:
            row = FakeMediaRow(
                id=self._next_id,
                platform=platform,
                video_id=video_id,
                title=title,
                source_url=source_url,
                duration=duration,
                thumbnail_url=thumbnail_url,
                metadata_json=metadata_json,
            )
            self._next_id += 1
            self.by_id[row.id] = row
            self.by_key[(platform, video_id)] = row
            return row
        existing.metadata_json = {**(metadata_json or {}), **(existing.metadata_json or {})}
        return existing


# --- Sprint 6 pipeline fakes ----------------------------------------------


@dataclass
class FakeJobRow:
    id: uuid.UUID
    user_id: int
    media_id: int
    format: str
    quality: str
    status: str
    priority: int = 1000
    retry_count: int = 0
    correlation_id: uuid.UUID | None = None
    error_message: str | None = None
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class FakeJobRepo:
    """In-memory ``JobRepositoryProtocol``."""

    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, FakeJobRow] = {}

    async def add(self, entity: FakeJobRow) -> FakeJobRow:
        self.jobs[entity.id] = entity
        return entity

    async def get_by_id(self, id_: Any) -> FakeJobRow | None:
        return self.jobs.get(id_)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[FakeJobRow]:
        return list(self.jobs.values())[offset : offset + limit]

    async def delete(self, entity: FakeJobRow) -> None:
        self.jobs.pop(entity.id, None)

    async def get_by_uuid(self, job_id: uuid.UUID) -> FakeJobRow | None:
        return self.jobs.get(job_id)

    async def count_active_for_user(
        self, user_id: int, *, within_seconds: int | None = None
    ) -> int:
        terminal = {"completed", "permanently_failed", "cancelled"}
        cutoff = (
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=within_seconds)
            if within_seconds is not None
            else None
        )
        return sum(
            1
            for j in self.jobs.values()
            if j.user_id == user_id
            and j.status not in terminal
            and (cutoff is None or j.created_at > cutoff)
        )

    async def create(
        self,
        *,
        job_id: uuid.UUID,
        user_id: int,
        media_id: int,
        format_: str,
        quality: str,
        priority: int,
        correlation_id: uuid.UUID | None,
        status: str,
    ) -> FakeJobRow:
        row = FakeJobRow(
            id=job_id,
            user_id=user_id,
            media_id=media_id,
            format=format_,
            quality=quality,
            status=status,
            priority=priority,
            correlation_id=correlation_id,
        )
        self.jobs[job_id] = row
        return row

    async def set_status(
        self,
        job_id: uuid.UUID,
        status: str,
        *,
        started_at: datetime.datetime | None = None,
        finished_at: datetime.datetime | None = None,
        error_message: str | None = None,
        increment_retry: bool = False,
    ) -> None:
        row = self.jobs.get(job_id)
        if row is None:
            return
        row.status = status
        if error_message is not None:
            row.error_message = error_message
        if increment_retry:
            row.retry_count += 1


@dataclass
class FakeCachedFileRow:
    id: int
    media_id: int
    format: str
    quality: str
    telegram_file_id: str
    telegram_unique_file_id: str
    file_size: int | None
    usage_count: int = 1


class FakeCachedFileRepo:
    """In-memory ``CachedFileRepositoryProtocol``."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[int, str, str], FakeCachedFileRow] = {}
        self.by_id: dict[int, FakeCachedFileRow] = {}
        self._next_id = 1

    async def add(self, entity: FakeCachedFileRow) -> FakeCachedFileRow:
        return entity

    async def get_by_id(self, id_: Any) -> FakeCachedFileRow | None:
        return self.by_id.get(id_)

    async def list_paginated(
        self, *, limit: int = 50, offset: int = 0
    ) -> Sequence[FakeCachedFileRow]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: FakeCachedFileRow) -> None:
        self.by_id.pop(entity.id, None)
        self.by_key.pop((entity.media_id, entity.format, entity.quality), None)

    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> FakeCachedFileRow | None:
        return self.by_key.get((media_id, format_, quality))

    async def upsert(
        self,
        *,
        media_id: int,
        format_: str,
        quality: str,
        telegram_file_id: str,
        telegram_unique_file_id: str,
        file_size: int | None,
    ) -> FakeCachedFileRow:
        key = (media_id, format_, quality)
        existing = self.by_key.get(key)
        if existing is not None:
            existing.telegram_file_id = telegram_file_id
            existing.telegram_unique_file_id = telegram_unique_file_id
            existing.file_size = file_size
            existing.usage_count += 1
            return existing
        row = FakeCachedFileRow(
            id=self._next_id,
            media_id=media_id,
            format=format_,
            quality=quality,
            telegram_file_id=telegram_file_id,
            telegram_unique_file_id=telegram_unique_file_id,
            file_size=file_size,
        )
        self._next_id += 1
        self.by_key[key] = row
        self.by_id[row.id] = row
        return row

    async def bump_usage(self, cached_file_id: int) -> None:
        row = self.by_id.get(cached_file_id)
        if row is not None:
            row.usage_count += 1


@dataclass
class FakeActiveDownloadRow:
    media_id: int
    format: str
    quality: str
    job_id: uuid.UUID


class FakeActiveDownloadRepo:
    """In-memory ``ActiveDownloadRepositoryProtocol``."""

    def __init__(self) -> None:
        self.by_key: dict[tuple[int, str, str], FakeActiveDownloadRow] = {}

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> Any:
        return None

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return list(self.by_key.values())[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        return None

    async def get_by_media_format_quality(
        self, media_id: int, format_: str, quality: str
    ) -> FakeActiveDownloadRow | None:
        return self.by_key.get((media_id, format_, quality))

    async def insert_if_absent(
        self, *, media_id: int, format_: str, quality: str, job_id: uuid.UUID
    ) -> bool:
        key = (media_id, format_, quality)
        if key in self.by_key:
            return False
        self.by_key[key] = FakeActiveDownloadRow(media_id, format_, quality, job_id)
        return True

    async def delete_by_job(self, job_id: uuid.UUID) -> int:
        before = len(self.by_key)
        self.by_key = {k: v for k, v in self.by_key.items() if v.job_id != job_id}
        return before - len(self.by_key)


@dataclass
class FakeWaiterRow:
    job_id: uuid.UUID
    user_id: int
    correlation_id: uuid.UUID | None = None


class FakeJobWaiterRepo:
    """In-memory ``JobWaiterRepositoryProtocol``."""

    def __init__(self) -> None:
        self.waiters: list[FakeWaiterRow] = []

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> Any:
        return None

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return self.waiters[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        return None

    async def list_for_job(self, job_id: uuid.UUID) -> Sequence[FakeWaiterRow]:
        return [w for w in self.waiters if w.job_id == job_id]

    async def delete_for_job(self, job_id: uuid.UUID) -> int:
        before = len(self.waiters)
        self.waiters = [w for w in self.waiters if w.job_id != job_id]
        return before - len(self.waiters)

    async def add_waiter(
        self, *, job_id: uuid.UUID, user_id: int, correlation_id: uuid.UUID | None
    ) -> bool:
        if any(w.job_id == job_id and w.user_id == user_id for w in self.waiters):
            return False
        self.waiters.append(FakeWaiterRow(job_id, user_id, correlation_id))
        return True


@dataclass
class FakeDownloadRow:
    user_id: int
    cached_file_id: int | None
    platform: str
    format: str
    quality: str
    file_size: int | None
    status: str = "completed"
    id: int = 0
    created_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )


class FakeDownloadRepo:
    """In-memory ``DownloadRepositoryProtocol``."""

    def __init__(self) -> None:
        self.rows: list[FakeDownloadRow] = []
        self._next_id = 1

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> Any:
        return None

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return self.rows[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        return None

    async def list_for_user(
        self, user_id: int, *, limit: int = 10, offset: int = 0
    ) -> Sequence[FakeDownloadRow]:
        owned = [r for r in self.rows if r.user_id == user_id]
        owned.sort(key=lambda r: (r.created_at, r.id), reverse=True)  # newest first
        return owned[offset : offset + limit]

    async def get_for_user(self, download_id: int, user_id: int) -> FakeDownloadRow | None:
        return next((r for r in self.rows if r.id == download_id and r.user_id == user_id), None)

    async def create_completed(
        self,
        *,
        user_id: int,
        cached_file_id: int | None,
        platform: str,
        format_: str,
        quality: str,
        file_size: int | None,
        status: str = "completed",
    ) -> FakeDownloadRow:
        row = FakeDownloadRow(
            user_id=user_id,
            cached_file_id=cached_file_id,
            platform=platform,
            format=format_,
            quality=quality,
            file_size=file_size,
            status=status,
            id=self._next_id,
        )
        self._next_id += 1
        self.rows.append(row)
        return row


class FakeQueueBackend:
    """In-memory ``QueueProtocol`` (lowest score first)."""

    def __init__(self) -> None:
        self.entries: list[tuple[float, str]] = []
        self.active: set[str] = set()

    async def enqueue(self, member: str, *, score: float) -> None:
        self.entries.append((score, member))
        self.entries.sort(key=lambda e: e[0])

    async def dequeue(self) -> str | None:
        if not self.entries:
            return None
        _, member = self.entries.pop(0)
        self.active.add(member)
        return member

    async def ack(self, member: str) -> None:
        self.active.discard(member)

    async def depth(self) -> int:
        return len(self.entries)

    async def active_count(self) -> int:
        return len(self.active)


class FakeFileSender:
    """In-memory ``FileSenderProtocol`` recording uploads and deliveries.

    ``uploads`` records the chat each file was uploaded to (the first waiter's
    delivery); ``sent`` records ``send_cached`` deliveries to additional waiters.
    """

    def __init__(
        self,
        *,
        file_id: str = "tg-file-id",
        unique: str = "tg-unique",
        send_cached_error: Exception | None = None,
    ) -> None:
        self._file_id = file_id
        self._unique = unique
        self._send_cached_error = send_cached_error
        self.uploads: list[tuple[int, Path]] = []
        self.filenames: list[str] = []
        self.sent: list[tuple[int, str]] = []
        self._next_message_id = 7000

    def _message_id(self) -> int:
        self._next_message_id += 1
        return self._next_message_id

    async def upload(
        self,
        path: Path,
        *,
        format_: MediaFormat,
        quality: Quality,
        chat_id: int,
        filename: str,
        caption: str | None = None,
    ) -> Any:
        from domain.protocols.file_sender import UploadedFile

        self.uploads.append((chat_id, path))
        self.filenames.append(filename)
        size = path.stat().st_size if path.exists() else None
        return UploadedFile(
            file_id=self._file_id,
            unique_file_id=self._unique,
            size_bytes=size,
            message_id=self._message_id(),
        )

    async def send_cached(
        self,
        telegram_id: int,
        file_id: str,
        *,
        format_: MediaFormat,
        quality: Quality,
        caption: str | None = None,
    ) -> int | None:
        if self._send_cached_error is not None:
            raise self._send_cached_error
        self.sent.append((telegram_id, file_id))
        return self._message_id()


class FakeMessageSender:
    """In-memory ``MessageSenderProtocol`` recording sends/edits."""

    def __init__(self) -> None:
        self._next_id = 100
        self.sent: list[tuple[int, str]] = []
        self.edits: list[tuple[int, int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> int:
        self._next_id += 1
        self.sent.append((chat_id, text))
        return self._next_id

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        self.edits.append((chat_id, message_id, text))


class FakeTranscoder:
    """In-memory ``TranscoderProtocol``: writes a target-extension file."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def transcode_audio(self, source: Path, target: Any) -> Path:
        self.calls.append(target.quality.value)
        dest = source.with_suffix(f".{target.container}")
        dest.write_bytes(b"transcoded-audio")
        return dest


class FakeFileDownloader:
    """A ``DownloaderProtocol`` whose ``download`` writes a real temp file."""

    def __init__(self, *, content: bytes = b"video-bytes", error: Exception | None = None) -> None:
        self.name = "fake"
        self.supported_platforms = {"*"}
        self.capabilities = {Capability.VIDEO, Capability.AUDIO}
        self.priority = 100
        self._content = content
        self._error = error
        self.calls = 0

    async def extract_info(self, url: str) -> MediaInfo:
        return MediaInfo(platform="generic", video_id="vid", title="T", source_url=url)

    async def download(
        self, media: MediaInfo, format_: MediaFormat, quality: Quality, dest: Path
    ) -> DownloadedFile:
        self.calls += 1
        if self._error is not None:
            raise self._error
        dest.mkdir(parents=True, exist_ok=True)
        ext = "m4a" if format_ is MediaFormat.AUDIO else "mp4"
        path = dest / f"{media.video_id}.{ext}"
        path.write_bytes(self._content)
        return DownloadedFile(
            path=path, size_bytes=len(self._content), format=format_, quality=quality
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth.OK


# --- Sprint 8 admin/broadcast fakes ---------------------------------------
@dataclass
class FakeBroadcastRow:
    id: int
    created_by: int
    message_text: str
    target_language: str | None = None
    target_role: str | None = None
    expected_total: int = 0
    total_sent: int = 0
    total_failed: int = 0
    status: str = "pending"
    completed_at: datetime.datetime | None = None
    advertisement_id: int | None = None


class FakeBroadcastRepo:
    """In-memory ``BroadcastRepositoryProtocol``."""

    def __init__(self) -> None:
        self.rows: list[FakeBroadcastRow] = []
        self._next_id = 1

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> FakeBroadcastRow | None:
        return next((b for b in self.rows if b.id == id_), None)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return self.rows[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        return None

    async def create_pending(
        self,
        *,
        created_by: int,
        message_text: str,
        target_language: str | None,
        target_role: str | None,
        expected_total: int,
        advertisement_id: int | None = None,
    ) -> FakeBroadcastRow:
        row = FakeBroadcastRow(
            id=self._next_id,
            created_by=created_by,
            message_text=message_text,
            target_language=target_language,
            target_role=target_role,
            expected_total=expected_total,
            advertisement_id=advertisement_id,
            status="pending",
        )
        self._next_id += 1
        self.rows.append(row)
        return row

    async def get_next_pending(self) -> FakeBroadcastRow | None:
        pending = sorted((b for b in self.rows if b.status == "pending"), key=lambda b: b.id)
        return pending[0] if pending else None

    async def set_status(
        self, broadcast_id: int, status: str, *, completed_at: datetime.datetime | None = None
    ) -> None:
        row = await self.get_by_id(broadcast_id)
        if row is not None:
            row.status = status
            if completed_at is not None:
                row.completed_at = completed_at

    async def add_counts(self, broadcast_id: int, *, sent: int, failed: int) -> None:
        row = await self.get_by_id(broadcast_id)
        if row is not None:
            row.total_sent += sent
            row.total_failed += failed


# --- Sprint 9 ad fakes ----------------------------------------------------
@dataclass
class FakeAdRow:
    id: int
    title: str
    type: str = "text"
    content_text: str | None = None
    content_media_file_id: str | None = None
    button_text: str | None = None
    button_url: str | None = None
    target_role: str | None = None
    show_every_n_downloads: int = 1
    is_active: bool = True
    priority: int = 0
    impressions: int = 0
    clicks: int = 0
    created_by: int = 1
    updated_at: datetime.datetime | None = None
    # Ads v2 (Sprint 9.5).
    placement: str = "post_download"
    delivery_mode: str = "fields"
    storage_chat_id: int | None = None
    storage_message_id: int | None = None
    parse_mode: str | None = None
    audience_mode: str = "all"


class FakeAdRepo:
    """In-memory ``AdRepositoryProtocol[FakeAdRow]``."""

    def __init__(self) -> None:
        self.by_id: dict[int, FakeAdRow] = {}
        self._next_id = 1

    async def add(self, entity: FakeAdRow) -> FakeAdRow:
        self.by_id[entity.id] = entity
        return entity

    async def get_by_id(self, id_: Any) -> FakeAdRow | None:
        return self.by_id.get(id_)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[FakeAdRow]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: FakeAdRow) -> None:
        self.by_id.pop(entity.id, None)

    def _ranked(self, ads: list[FakeAdRow]) -> list[FakeAdRow]:
        return sorted(ads, key=lambda a: (-a.priority, a.id))

    async def list_active_for_role(self, effective_role: str) -> Sequence[FakeAdRow]:
        matching = [
            a
            for a in self.by_id.values()
            if a.is_active and (a.target_role is None or a.target_role == effective_role)
        ]
        return self._ranked(matching)

    async def list_active_for_placement(self, placement: str) -> Sequence[FakeAdRow]:
        matching = [a for a in self.by_id.values() if a.is_active and a.placement == placement]
        return self._ranked(matching)

    async def list_all_ads(self) -> Sequence[FakeAdRow]:
        return self._ranked(list(self.by_id.values()))

    async def create_ad(
        self,
        *,
        title: str,
        ad_type: str,
        content_text: str | None,
        content_media_file_id: str | None,
        button_text: str | None,
        button_url: str | None,
        target_role: str | None,
        show_every_n_downloads: int,
        priority: int,
        created_by: int,
        placement: str = "post_download",
        delivery_mode: str = "fields",
        storage_chat_id: int | None = None,
        storage_message_id: int | None = None,
        parse_mode: str | None = None,
        audience_mode: str = "all",
    ) -> FakeAdRow:
        row = FakeAdRow(
            id=self._next_id,
            title=title,
            type=ad_type,
            content_text=content_text,
            content_media_file_id=content_media_file_id,
            button_text=button_text,
            button_url=button_url,
            target_role=target_role,
            show_every_n_downloads=show_every_n_downloads,
            priority=priority,
            created_by=created_by,
            placement=placement,
            delivery_mode=delivery_mode,
            storage_chat_id=storage_chat_id,
            storage_message_id=storage_message_id,
            parse_mode=parse_mode,
            audience_mode=audience_mode,
        )
        self._next_id += 1
        self.by_id[row.id] = row
        return row

    async def apply_update(self, ad: FakeAdRow, changes: dict[str, Any]) -> FakeAdRow:
        for key, value in changes.items():
            setattr(ad, key, value)
        ad.updated_at = datetime.datetime.now(datetime.UTC)
        return ad

    async def increment_impressions(self, ad_id: int) -> None:
        row = self.by_id.get(ad_id)
        if row is not None:
            row.impressions += 1

    async def increment_clicks(self, ad_id: int) -> None:
        row = self.by_id.get(ad_id)
        if row is not None:
            row.clicks += 1


class FakeAdSender:
    """In-memory ``AdSenderProtocol`` recording each ad sent (Sprint 9.5)."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.sent: list[dict[str, Any]] = []
        self.copied: list[dict[str, Any]] = []

    async def send_ad(
        self,
        chat_id: int,
        *,
        ad_type: str,
        text: str | None,
        media_file_id: str | None,
        buttons: Sequence[Any],
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        if self._error is not None:
            raise self._error
        self.sent.append(
            {
                "chat_id": chat_id,
                "ad_type": ad_type,
                "text": text,
                "media_file_id": media_file_id,
                "buttons": list(buttons),
                "parse_mode": parse_mode,
                "reply_to_message_id": reply_to_message_id,
            }
        )

    async def copy_ad(
        self,
        chat_id: int,
        *,
        from_chat_id: int,
        message_id: int,
        buttons: Sequence[Any],
        reply_to_message_id: int | None = None,
    ) -> None:
        if self._error is not None:
            raise self._error
        self.copied.append(
            {
                "chat_id": chat_id,
                "from_chat_id": from_chat_id,
                "message_id": message_id,
                "buttons": list(buttons),
                "reply_to_message_id": reply_to_message_id,
            }
        )


@dataclass
class FakeAdButtonRow:
    id: int
    advertisement_id: int
    text: str
    url: str | None
    row: int = 0
    position: int = 0
    clicks: int = 0


class FakeAdButtonRepo:
    """In-memory ``AdButtonRepositoryProtocol``."""

    def __init__(self) -> None:
        self.by_id: dict[int, FakeAdButtonRow] = {}
        self._next_id = 1

    async def add(self, entity: FakeAdButtonRow) -> FakeAdButtonRow:
        self.by_id[entity.id] = entity
        return entity

    async def get_by_id(self, id_: Any) -> FakeAdButtonRow | None:
        return self.by_id.get(id_)

    async def list_paginated(
        self, *, limit: int = 50, offset: int = 0
    ) -> Sequence[FakeAdButtonRow]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: FakeAdButtonRow) -> None:
        self.by_id.pop(entity.id, None)

    async def list_for_ad(self, ad_id: int) -> Sequence[FakeAdButtonRow]:
        rows = [b for b in self.by_id.values() if b.advertisement_id == ad_id]
        return sorted(rows, key=lambda b: (b.row, b.position, b.id))

    async def create_button(
        self, *, advertisement_id: int, text: str, url: str | None, row: int, position: int
    ) -> FakeAdButtonRow:
        button = FakeAdButtonRow(
            id=self._next_id,
            advertisement_id=advertisement_id,
            text=text,
            url=url,
            row=row,
            position=position,
        )
        self._next_id += 1
        self.by_id[button.id] = button
        return button

    async def delete_for_ad(self, ad_id: int) -> int:
        ids = [bid for bid, b in self.by_id.items() if b.advertisement_id == ad_id]
        for bid in ids:
            del self.by_id[bid]
        return len(ids)

    async def increment_clicks(self, button_id: int) -> None:
        button = self.by_id.get(button_id)
        if button is not None:
            button.clicks += 1


@dataclass
class FakeAudienceRuleRow:
    id: int
    advertisement_id: int
    effect: str
    dimension: str
    value: str


class FakeAudienceRuleRepo:
    """In-memory ``AdAudienceRuleRepositoryProtocol``."""

    def __init__(self) -> None:
        self.by_id: dict[int, FakeAudienceRuleRow] = {}
        self._next_id = 1

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> FakeAudienceRuleRow | None:
        return self.by_id.get(id_)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        self.by_id.pop(entity.id, None)

    async def list_for_ad(self, ad_id: int) -> Sequence[FakeAudienceRuleRow]:
        return [r for r in self.by_id.values() if r.advertisement_id == ad_id]

    async def create_rule(
        self, *, advertisement_id: int, effect: str, dimension: str, value: str
    ) -> FakeAudienceRuleRow:
        rule = FakeAudienceRuleRow(
            id=self._next_id,
            advertisement_id=advertisement_id,
            effect=effect,
            dimension=dimension,
            value=value,
        )
        self._next_id += 1
        self.by_id[rule.id] = rule
        return rule

    async def delete_for_ad(self, ad_id: int) -> int:
        ids = [rid for rid, r in self.by_id.items() if r.advertisement_id == ad_id]
        for rid in ids:
            del self.by_id[rid]
        return len(ids)


class FakeSegmentMemberRepo:
    """In-memory ``AudienceSegmentMemberRepositoryProtocol``."""

    def __init__(self) -> None:
        self.members: set[tuple[int, int]] = set()

    async def add_member(self, *, segment_id: int, user_id: int) -> bool:
        key = (segment_id, user_id)
        if key in self.members:
            return False
        self.members.add(key)
        return True

    async def remove_member(self, *, segment_id: int, user_id: int) -> bool:
        key = (segment_id, user_id)
        if key in self.members:
            self.members.discard(key)
            return True
        return False

    async def list_segment_ids_for_user(self, user_id: int) -> set[int]:
        return {s for s, u in self.members if u == user_id}

    async def count_members(self, segment_id: int) -> int:
        return sum(1 for s, _ in self.members if s == segment_id)


@dataclass
class FakeSegmentRow:
    id: int
    name: str
    description: str | None = None
    created_by: int = 1


class FakeSegmentRepo:
    """In-memory ``AudienceSegmentRepositoryProtocol``."""

    def __init__(self) -> None:
        self.by_id: dict[int, FakeSegmentRow] = {}
        self._next_id = 1

    async def add(self, entity: Any) -> Any:
        return entity

    async def get_by_id(self, id_: Any) -> FakeSegmentRow | None:
        return self.by_id.get(id_)

    async def list_paginated(self, *, limit: int = 50, offset: int = 0) -> Sequence[Any]:
        return list(self.by_id.values())[offset : offset + limit]

    async def delete(self, entity: Any) -> None:
        self.by_id.pop(entity.id, None)

    async def create_segment(
        self, *, name: str, description: str | None, created_by: int
    ) -> FakeSegmentRow:
        row = FakeSegmentRow(
            id=self._next_id, name=name, description=description, created_by=created_by
        )
        self._next_id += 1
        self.by_id[row.id] = row
        return row

    async def get_by_name(self, name: str) -> FakeSegmentRow | None:
        return next((s for s in self.by_id.values() if s.name == name), None)

    async def list_all_segments(self) -> Sequence[FakeSegmentRow]:
        return sorted(self.by_id.values(), key=lambda s: s.id)
