"""Unit tests for DownloadService end-to-end + retry logic (MASTER_PLAN Task 6.5)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from core.uuid7 import uuid7
from domain.entities.media import MediaInfo
from domain.enums import JobStatus, MediaFormat, Quality
from domain.exceptions import ExtractionFailedError, FileTooLargeError
from domain.protocols.downloader import ProviderRetryElsewhere
from services.download_service import DownloadService, _safe_filename
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from services.url_analyzer import URLAnalyzerService
from tests.unit._fakes import (
    DEFAULT_RATE_SETTINGS,
    FakeActiveDownloadRepo,
    FakeCache,
    FakeCachedFileRepo,
    FakeDownloadRepo,
    FakeFileDownloader,
    FakeFileSender,
    FakeJobRepo,
    FakeJobWaiterRepo,
    FakeMediaRepo,
    FakeMessageSender,
    FakeProvider,
    FakeSettingsStore,
    FakeTranscoder,
    FakeUser,
    FakeUserRepo,
    load_settings,
    make_cache_service,
)

_INFO = MediaInfo(platform="youtube", video_id="vid", title="Clip", source_url="https://x/clip")


def _settings_store() -> FakeSettingsStore:
    data = dict(DEFAULT_RATE_SETTINGS)
    data["max_file_size"] = ("2147483648", "int")
    return FakeSettingsStore(data)


def _build(
    *,
    downloader: Any,
    temp_dir: Path,
    settings_store: FakeSettingsStore | None = None,
) -> dict[str, Any]:
    cache_service, _ = make_cache_service()
    settings = load_settings()
    settings.download_temp_dir = str(temp_dir)
    media_repo = FakeMediaRepo()
    env: dict[str, Any] = {
        "jobs": FakeJobRepo(),
        "cached": FakeCachedFileRepo(),
        "downloads": FakeDownloadRepo(),
        "waiters": FakeJobWaiterRepo(),
        "active": FakeActiveDownloadRepo(),
        "users": FakeUserRepo(),
        "sender": FakeFileSender(),
        "transcoder": FakeTranscoder(),
        "media_repo": media_repo,
        "cache_service": cache_service,
    }
    analyzer = URLAnalyzerService(FakeProvider("p", result=_INFO), cache_service, media_repo)
    settings_service = SettingsService(
        settings_store or _settings_store(), FakeCache(), cache_ttl=60
    )
    env["service"] = DownloadService(
        job_repo=env["jobs"],
        cached_file_repo=env["cached"],
        download_repo=env["downloads"],
        job_waiter_repo=env["waiters"],
        active_download_repo=env["active"],
        user_repo=env["users"],
        analyzer=analyzer,
        downloader=downloader,
        transcoder=env["transcoder"],
        file_sender=env["sender"],
        notification_service=NotificationService(FakeMessageSender()),
        cache_service=cache_service,
        settings_service=settings_service,
        settings=settings,
    )
    return env


async def _seed_job(env: dict[str, Any], fmt: MediaFormat, quality: Quality) -> str:
    media_repo: FakeMediaRepo = env["media_repo"]
    row = await media_repo.upsert_metadata(
        platform="youtube", video_id="vid", title="Clip", source_url=_INFO.source_url
    )
    job_id = uuid7()
    users: FakeUserRepo = env["users"]
    users.by_tid[555] = FakeUser(id=7, telegram_id=555)
    await env["jobs"].create(
        job_id=job_id,
        user_id=7,
        media_id=row.id,
        format_=fmt.value,
        quality=quality.value,
        priority=1000,
        correlation_id=None,
        status=JobStatus.QUEUED.value,
    )
    await env["waiters"].add_waiter(job_id=job_id, user_id=7, correlation_id=None)
    await env["active"].insert_if_absent(
        media_id=row.id, format_=fmt.value, quality=quality.value, job_id=job_id
    )
    return str(job_id)


async def test_video_happy_path(tmp_path: Path) -> None:
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)

    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.COMPLETED.value
    # Single waiter (the originator) is delivered exactly once — via the upload itself,
    # never a second send_cached (the duplicate-delivery bug).
    assert [chat for chat, _ in env["sender"].uploads] == [555]
    assert env["sender"].sent == []
    assert len(env["cached"].by_id) == 1
    assert len(env["downloads"].rows) == 1
    assert env["users"].by_tid[555].total_downloads == 1
    assert env["waiters"].waiters == []
    assert env["active"].by_key == {}
    assert not (tmp_path / job_id).exists()  # temp dir wiped


async def test_delivered_filename_uses_sanitized_title(tmp_path: Path) -> None:
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)

    # _INFO.title == "Clip"; the produced file is .mp4 → "Clip.mp4" (not vid123.mp4).
    assert env["sender"].filenames == ["Clip.mp4"]


@pytest.mark.parametrize(
    ("title", "suffix", "expected"),
    [
        ("Song: Title?", ".mp3", "Song Title.mp3"),
        ('a/b\\c:d*e"f<g>h|i', ".m4a", "abcdefghi.m4a"),
        ("   ", ".wav", "media.wav"),
        ("ok.", ".flac", "ok.flac"),
    ],
)
def test_safe_filename(title: str, suffix: str, expected: str) -> None:
    assert _safe_filename(title, suffix) == expected


async def test_audio_target_is_transcoded(tmp_path: Path) -> None:
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.AUDIO, Quality.MP3)

    await env["service"].process(job_id)

    assert env["transcoder"].calls == ["mp3"]
    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.COMPLETED.value


async def test_oversize_file_raises(tmp_path: Path) -> None:
    store = _settings_store()
    store._data["max_file_size"] = ("10", "int")  # 10 bytes — anything exceeds it
    env = _build(
        downloader=FakeFileDownloader(content=b"way-too-many-bytes"),
        temp_dir=tmp_path,
        settings_store=store,
    )
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    with pytest.raises(FileTooLargeError):
        await env["service"].process(job_id)
    assert env["sender"].sent == []  # nothing delivered


async def test_handle_failure_retries_then_permanently_fails(tmp_path: Path) -> None:
    env = _build(
        downloader=FakeFileDownloader(error=ProviderRetryElsewhere("boom")), temp_dir=tmp_path
    )
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    service: DownloadService = env["service"]
    jobs: FakeJobRepo = env["jobs"]

    for _ in range(3):  # retries left → re-queued
        assert await service.handle_failure(job_id, reason="boom", retryable=True, max_retries=3)
    # Retry budget exhausted → permanent.
    assert not await service.handle_failure(job_id, reason="boom", retryable=True, max_retries=3)
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.PERMANENTLY_FAILED.value


async def test_handle_failure_non_retryable_is_permanent(tmp_path: Path) -> None:
    env = _build(
        downloader=FakeFileDownloader(error=ExtractionFailedError("gone")), temp_dir=tmp_path
    )
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    service: DownloadService = env["service"]

    assert not await service.handle_failure(job_id, reason="gone", retryable=False, max_retries=3)
    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.PERMANENTLY_FAILED.value
