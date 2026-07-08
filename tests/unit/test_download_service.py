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


class RecordingAdHook:
    """An ``AdShowProtocol`` stub that records each post-delivery ad invocation."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def maybe_show(
        self,
        *,
        chat_id: int,
        role: str,
        is_premium: bool,
        premium_expires_at: Any,
        total_downloads: int,
        language: str | None = None,
        telegram_id: int | None = None,
        user_row_id: int | None = None,
        placement: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> bool:
        self.calls.append(
            {
                "chat_id": chat_id,
                "role": role,
                "is_premium": is_premium,
                "total_downloads": total_downloads,
                "reply_to_message_id": reply_to_message_id,
            }
        )
        return True


def _build(
    *,
    downloader: Any,
    temp_dir: Path,
    settings_store: FakeSettingsStore | None = None,
    ad_service: Any = None,
    caption_mixer: Any = None,
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
    env["msg"] = FakeMessageSender()
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
        notification_service=NotificationService(env["msg"]),
        cache_service=cache_service,
        settings_service=settings_service,
        settings=settings,
        ad_service=ad_service,
        caption_mixer=caption_mixer,
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
    # The originator's progress entry, as JobService.request would have stashed it.
    await env["cache_service"].set_job_context(
        str(job_id),
        {"progress": {"7": {"telegram_id": 555, "message_id": 901}}},
        ttl=600,
    )
    return str(job_id)


async def _add_second_waiter(env: dict[str, Any], job_id: str) -> None:
    """A second user (id 8 / tg 556) joins the same job via the fan-out path (16.4)."""
    users: FakeUserRepo = env["users"]
    users.by_tid[556] = FakeUser(id=8, telegram_id=556)
    await env["waiters"].add_waiter(job_id=uuid.UUID(job_id), user_id=8, correlation_id=None)
    await env["cache_service"].add_waiter_progress(job_id, 8, 556, 902)


async def test_video_happy_path(tmp_path: Path) -> None:
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)

    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.COMPLETED.value


async def test_caption_ad_rides_on_the_delivered_media(tmp_path: Path) -> None:
    # Two-layer ads: a caption ad's text + button are injected into the delivered media's
    # own caption/keyboard (same message), via the shared mixer — no separate message.
    from domain.protocols.advertising import AdButtonSpec
    from services.ad_service import CaptionAd
    from services.caption_ad_mixer import CaptionAdMixer

    class _CaptionAds:
        async def select_caption_ad(self, **_kw: Any) -> CaptionAd:
            return CaptionAd(text="Subscribe!", buttons=(AdButtonSpec("Go", url="https://x"),))

    env = _build(
        downloader=FakeFileDownloader(),
        temp_dir=tmp_path,
        caption_mixer=CaptionAdMixer(_CaptionAds()),  # type: ignore[arg-type]
    )
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)

    sender: Any = env["sender"]
    assert any(c and "Subscribe!" in c for c in sender.captions)  # ad text in the caption
    assert any(bs for bs in sender.button_sets)  # ad button rode on the media
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


async def test_fan_out_delivers_to_all_waiters_once(tmp_path: Path) -> None:
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    await _add_second_waiter(env, job_id)

    await env["service"].process(job_id)

    # The first waiter is delivered via the upload; the second via send_cached. Each
    # receives the file exactly once; only one cache entry is minted.
    assert [chat for chat, _ in env["sender"].uploads] == [555]
    assert env["sender"].sent == [(556, "tg-file-id")]
    assert len(env["cached"].by_id) == 1
    # One downloads row + one counter increment per waiter.
    assert sorted(r.user_id for r in env["downloads"].rows) == [7, 8]
    assert env["users"].by_tid[555].total_downloads == 1
    assert env["users"].by_tid[556].total_downloads == 1
    # Both waiters' progress messages are edited to the completed text.
    completed_targets = {(c, m) for c, m, _ in env["msg"].edits}
    assert (555, 901) in completed_targets and (556, 902) in completed_targets


async def test_retry_after_partial_delivery_is_idempotent(tmp_path: Path) -> None:
    # Model a retry: a prior attempt minted the file_id and delivered to waiter 7, then
    # failed (rolling back its DB writes). The persisted Redis context records both.
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    await _add_second_waiter(env, job_id)
    await env["cache_service"].record_uploaded_file(job_id, "minted-fid", "minted-unique")
    await env["cache_service"].record_delivered(job_id, 7)

    await env["service"].process(job_id)

    # No re-upload (so waiter 7 is NOT delivered to again); only waiter 8 is sent the file.
    assert env["sender"].uploads == []
    assert env["sender"].sent == [(556, "minted-fid")]
    # DB rows were rolled back on the prior attempt, so both are (re)created now.
    assert sorted(r.user_id for r in env["downloads"].rows) == [7, 8]
    assert env["users"].by_tid[555].total_downloads == 1
    assert env["users"].by_tid[556].total_downloads == 1


async def test_one_waiter_delivery_failure_does_not_block_others(tmp_path: Path) -> None:
    # The second waiter's send_cached fails; the first (via upload) still succeeds and
    # the job completes (risk-table mitigation: log + continue, never block the rest).
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path)
    env["sender"]._send_cached_error = RuntimeError("telegram hiccup")
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    await _add_second_waiter(env, job_id)

    await env["service"].process(job_id)

    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.COMPLETED.value
    assert [chat for chat, _ in env["sender"].uploads] == [555]  # first waiter delivered


async def test_handle_failure_non_retryable_is_permanent(tmp_path: Path) -> None:
    env = _build(
        downloader=FakeFileDownloader(error=ExtractionFailedError("gone")), temp_dir=tmp_path
    )
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    service: DownloadService = env["service"]

    assert not await service.handle_failure(job_id, reason="gone", retryable=False, max_retries=3)
    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.PERMANENTLY_FAILED.value


# --- ad hook (Task 9.3, flow 16.7) ----------------------------------------
async def test_ad_hook_runs_once_with_post_increment_total(tmp_path: Path) -> None:
    hook = RecordingAdHook()
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path, ad_service=hook)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)

    # The single waiter is offered an ad once, with their post-increment total (0 → 1),
    # attached as a reply to the delivered media (#30 — reply_to_message_id is set).
    assert len(hook.calls) == 1
    call = hook.calls[0]
    assert call["chat_id"] == 555 and call["total_downloads"] == 1
    assert call["reply_to_message_id"] is not None


async def test_ad_hook_fires_per_waiter_on_fan_out(tmp_path: Path) -> None:
    hook = RecordingAdHook()
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path, ad_service=hook)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    await _add_second_waiter(env, job_id)

    await env["service"].process(job_id)

    chats = sorted(call["chat_id"] for call in hook.calls)
    assert chats == [555, 556]
    assert all(call["total_downloads"] == 1 for call in hook.calls)


async def test_ad_hook_skips_waiters_delivered_on_a_prior_attempt(tmp_path: Path) -> None:
    # Retry after partial delivery: waiter 7 already had the file (prior attempt), so
    # only the newly-delivered waiter 8 is offered an ad — a retry never re-shows one.
    hook = RecordingAdHook()
    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path, ad_service=hook)
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)
    await _add_second_waiter(env, job_id)
    await env["cache_service"].record_uploaded_file(job_id, "minted-fid", "minted-unique")
    await env["cache_service"].record_delivered(job_id, 7)

    await env["service"].process(job_id)

    assert [call["chat_id"] for call in hook.calls] == [556]


async def test_ad_hook_failure_never_fails_the_job(tmp_path: Path) -> None:
    class _BoomHook:
        async def maybe_show(self, **_kwargs: Any) -> bool:
            raise RuntimeError("ad subsystem down")

    env = _build(downloader=FakeFileDownloader(), temp_dir=tmp_path, ad_service=_BoomHook())
    job_id = await _seed_job(env, MediaFormat.VIDEO, Quality.P720)

    await env["service"].process(job_id)  # must not raise

    jobs: FakeJobRepo = env["jobs"]
    assert jobs.jobs[uuid.UUID(job_id)].status == JobStatus.COMPLETED.value
