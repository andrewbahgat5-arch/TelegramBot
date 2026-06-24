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


class FakeDownloadRepo:
    """In-memory ``DownloadRepositoryProtocol``."""

    def __init__(self) -> None:
        self.rows: list[FakeDownloadRow] = []

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
        return [r for r in self.rows if r.user_id == user_id][offset : offset + limit]

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
        )
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
        return UploadedFile(file_id=self._file_id, unique_file_id=self._unique, size_bytes=size)

    async def send_cached(
        self,
        telegram_id: int,
        file_id: str,
        *,
        format_: MediaFormat,
        quality: Quality,
        caption: str | None = None,
    ) -> None:
        if self._send_cached_error is not None:
            raise self._send_cached_error
        self.sent.append((telegram_id, file_id))


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
