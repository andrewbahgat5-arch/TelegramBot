"""Unit tests for YtdlpProvider (MASTER_PLAN Task 5.3).

The subprocess is faked (no real yt-dlp), so these exercise JSON parsing, format
extraction, and vendor-error mapping deterministically.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import orjson
import pytest

from domain.entities.media import MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import ExtractionFailedError, URLNotSupportedError
from domain.protocols.downloader import ProviderHealth, ProviderRetryElsewhere
from infrastructure.downloader.providers.ytdlp_provider import (
    YtdlpProvider,
    _format_selector,
    _map_error,
    _quality_for_format,
)

_INFO: dict[str, Any] = {
    "id": "vid123",
    "title": "Cool Video",
    "webpage_url": "https://www.youtube.com/watch?v=vid123",
    "duration": 212,
    "thumbnail": "https://t/img.jpg",
    "uploader": "Chan",
    "view_count": 1000,
    "formats": [
        {"format_id": "137", "vcodec": "avc1", "acodec": "none", "height": 1080, "filesize": 5_000},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a", "filesize": 400},
        {"format_id": "18", "vcodec": "avc1", "acodec": "mp4a", "height": 360},
        {"format_id": "sb0", "vcodec": "none", "acodec": "none"},  # storyboard → skipped
    ],
}

_URL = "https://www.youtube.com/watch?v=vid123"


class _FakeProc:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int, *, timeout: bool = False):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self._timeout = timeout
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._timeout:
            raise TimeoutError
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


def _patch_proc(monkeypatch: pytest.MonkeyPatch, proc: _FakeProc) -> None:
    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)


def test_to_media_info_parses_formats() -> None:
    provider = YtdlpProvider()
    info = provider._to_media_info(_URL, _INFO)
    assert info.video_id == "vid123"
    assert info.title == "Cool Video"
    assert info.duration == 212
    assert info.platform == "youtube"
    # 137 (video 1080p), 140 (audio), 18 (video 360p) → 3 options; storyboard skipped.
    assert len(info.formats) == 3
    hd = next(o for o in info.formats if o.provider_format_id == "137")
    assert hd.format is MediaFormat.VIDEO and hd.quality is Quality.P1080
    audio = next(o for o in info.formats if o.provider_format_id == "140")
    assert audio.format is MediaFormat.AUDIO


def test_to_media_info_emits_image_when_no_video_formats() -> None:
    """An image-only source (e.g. a Pinterest image pin) → one IMAGE option carrying
    the full-resolution /originals/ URL, so it auto-downloads and delivers as a photo."""
    provider = YtdlpProvider()
    image_info: dict[str, Any] = {
        "id": "pin123",
        "title": "A knight",
        "webpage_url": "https://www.pinterest.com/pin/pin123/",
        "formats": [],
        "thumbnails": [
            {"url": "https://i.pinimg.com/236x/x.jpg", "width": 236, "height": 300},
            {"url": "https://i.pinimg.com/originals/x.jpg", "width": 736, "height": 900},
        ],
    }
    info = provider._to_media_info("https://www.pinterest.com/pin/pin123/", image_info)
    assert len(info.formats) == 1
    option = info.formats[0]
    assert option.format is MediaFormat.IMAGE
    assert option.quality is Quality.IMAGE
    assert option.provider_format_id == "https://i.pinimg.com/originals/x.jpg"


def test_youtube_no_formats_raises_instead_of_delivering_a_photo() -> None:
    """A named video platform (YouTube) that extracts no playable formats — e.g. a
    transient bot-block returning only metadata + a storyboard/thumbnail under
    ``--ignore-no-formats-error`` — must RAISE, never deliver the storyboard/thumbnail as a
    photo (the bug where users received a storyboard grid instead of the video)."""
    provider = YtdlpProvider()
    blocked: dict[str, Any] = {
        "id": "GQ-PjWVVzzo",
        "title": "A 4K video",
        "webpage_url": "https://www.youtube.com/watch?v=GQ-PjWVVzzo",
        "formats": [
            {
                "format_id": "sb0",
                "vcodec": "none",
                "acodec": "none",
                "ext": "mhtml",
                "url": "https://i.ytimg.com/sb/GQ-PjWVVzzo/storyboard3_L2/M0.jpg",
            }
        ],
        "thumbnails": [
            {"url": "https://i.ytimg.com/vi/GQ-PjWVVzzo/maxres.jpg", "width": 1280, "height": 720}
        ],
    }
    with pytest.raises(ProviderRetryElsewhere):
        provider._to_media_info("https://www.youtube.com/watch?v=GQ-PjWVVzzo", blocked)


@pytest.mark.parametrize(
    ("width", "height", "note", "expected"),
    [
        # Regression: a wide ~1.9:1 4K video reports 3840x2026, not x2160. It must
        # map to 2160p, not 1440p (the old height-floor bug).
        (3840, 2026, "2160p", Quality.P2160),
        (3840, 2026, None, Quality.P2160),  # no note → longer-edge wins
        (2560, 1350, "1440p", Quality.P1440),
        (1920, 1080, "1080p60", Quality.P1080),  # fps suffix tolerated
        (1080, 1920, None, Quality.P1080),  # portrait: long edge = height
        (None, 720, None, Quality.P720),  # height-only landscape
    ],
)
def test_quality_for_format_handles_non_16x9(
    width: int | None, height: int | None, note: str | None, expected: Quality
) -> None:
    assert _quality_for_format(width, height, note) is expected


@pytest.mark.parametrize(
    ("stderr", "exc"),
    [
        ("ERROR: Unsupported URL: foo", URLNotSupportedError),
        ("ERROR: Video unavailable", ExtractionFailedError),
        ("ERROR: Private video. Sign in if you've been granted access", ExtractionFailedError),
        ("ERROR: This video has been removed by the uploader", ExtractionFailedError),
        ("ERROR: HTTP Error 503", ProviderRetryElsewhere),
        # #12 reclassifications: these intermittent failures are now transient (were
        # previously permanent / mis-labelled as "content"), so they get retried.
        ("ERROR: HTTP Error 429: Too Many Requests", ProviderRetryElsewhere),
        ("ERROR: Sign in to confirm you're not a bot", ProviderRetryElsewhere),
        ("ERROR: unable to extract player response", ProviderRetryElsewhere),
        ("ERROR: Unable to download webpage: nsig extraction failed", ProviderRetryElsewhere),
        # Interrupted media transfer on large streams (403/reset mid-download): now transient
        # so the job retries instead of permanently failing on a re-downloadable condition.
        ("ERROR: unable to download video data: HTTP Error 403: Forbidden", ProviderRetryElsewhere),
        (
            "ERROR: Unable to rename file: [Errno 2] No such file or directory: "
            "'/tmp/x/v.f299.mp4.part' -> '/tmp/x/v.f299.mp4'",
            ProviderRetryElsewhere,
        ),
        ("ERROR: something weird", ExtractionFailedError),  # unknown stays permanent (safe)
    ],
)
def test_map_error(stderr: str, exc: type[Exception]) -> None:
    assert isinstance(_map_error(stderr), exc)


async def test_extract_info_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_INFO), b"", 0))
    info = await YtdlpProvider().extract_info(_URL)
    assert info.video_id == "vid123"
    assert len(info.formats) == 3


async def test_extract_info_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(b"", b"ERROR: Unsupported URL: foo", 1))
    with pytest.raises(URLNotSupportedError):
        await YtdlpProvider().extract_info(_URL)


async def test_extract_info_timeout_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _FakeProc(b"", b"", 0, timeout=True)
    _patch_proc(monkeypatch, proc)
    with pytest.raises(ProviderRetryElsewhere):
        await YtdlpProvider().extract_info(_URL)
    assert proc.killed


def _patch_proc_seq(monkeypatch: pytest.MonkeyPatch, procs: list[_FakeProc]) -> dict[str, int]:
    """Return a different fake proc per subprocess call, so retries can be exercised."""
    state = {"calls": 0}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        proc = procs[min(state["calls"], len(procs) - 1)]
        state["calls"] += 1
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def no_sleep(_seconds: float) -> None:  # keep retry tests fast
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    return state


async def test_extract_info_retries_transient_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A transient bot-check on the first attempt, then a clean run — the retry recovers it
    # instead of surfacing "couldn't read that link" (#12).
    procs = [
        _FakeProc(b"", b"ERROR: Sign in to confirm you're not a bot", 1),
        _FakeProc(orjson.dumps(_INFO), b"", 0),
    ]
    state = _patch_proc_seq(monkeypatch, procs)
    info = await YtdlpProvider().extract_info(_URL)
    assert info.video_id == "vid123"
    assert state["calls"] == 2  # one retry


async def test_extract_info_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    # A persistent transient failure eventually surfaces as retryable (the handler maps it to
    # a "try again" message), not a false "private/removed".
    proc = _FakeProc(b"", b"ERROR: HTTP Error 429: Too Many Requests", 1)
    state = _patch_proc_seq(monkeypatch, [proc])
    with pytest.raises(ProviderRetryElsewhere):
        await YtdlpProvider().extract_info(_URL)
    assert state["calls"] == 3  # initial + 2 retries


async def test_extract_info_does_not_retry_permanent_content_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _FakeProc(b"", b"ERROR: Private video", 1)
    state = _patch_proc_seq(monkeypatch, [proc])
    with pytest.raises(ExtractionFailedError):
        await YtdlpProvider().extract_info(_URL)
    assert state["calls"] == 1  # no retry for a permanent failure


async def test_extract_info_bad_json_is_extraction_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(b"not json", b"", 0))
    with pytest.raises(ExtractionFailedError):
        await YtdlpProvider().extract_info(_URL)


async def test_download_returns_produced_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The (faked) subprocess is a no-op; we pre-create the file it "produces".
    (tmp_path / "vid.mp4").write_bytes(b"x" * 100)
    _patch_proc(monkeypatch, _FakeProc(b"", b"", 0))
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    result = await YtdlpProvider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert result.path.name == "vid.mp4"
    assert result.size_bytes == 100


async def test_video_download_requests_mp4_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    await YtdlpProvider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert "--merge-output-format" in captured["args"]
    assert "mp4" in captured["args"]


async def test_audio_download_skips_mp4_merge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.m4a").write_bytes(b"x" * 10)
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    await YtdlpProvider().download(media, MediaFormat.AUDIO, Quality.MP3, tmp_path)
    assert "--merge-output-format" not in captured["args"]


async def test_proxy_fast_path_uses_aria2c_and_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    provider = YtdlpProvider(proxy="http://u:p@res.example:7577")
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    await provider.download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    args = captured["args"]
    assert "aria2c" in args and "--downloader" in args  # fast aria2c path
    assert "--proxy" in args and "http://u:p@res.example:7577" in args  # via residential proxy


async def test_proxy_fast_path_falls_back_to_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        calls.append(args)
        if len(calls) == 1:  # aria2c/residential fast path fails
            return _FakeProc(b"", b"ERROR: proxy connection failed", 1)
        (tmp_path / "vid.mp4").write_bytes(b"x" * 30)  # native fallback succeeds
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    provider = YtdlpProvider(proxy="http://u:p@res.example:7577")
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    result = await provider.download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert result.size_bytes == 30 and len(calls) == 2
    assert "aria2c" in calls[0]  # fast path first
    # fallback is native and does NOT force the residential proxy (uses the config proxy)
    assert "aria2c" not in calls[1] and "--proxy" not in calls[1]


async def test_no_proxy_uses_native_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    media = MediaInfo(platform="youtube", video_id="vid", title="T", source_url=_URL)
    await YtdlpProvider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)  # no proxy
    assert "aria2c" not in captured["args"]  # no fast path without a proxy


async def test_download_no_file_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_proc(monkeypatch, _FakeProc(b"", b"", 0))
    media = MediaInfo(platform="youtube", video_id="missing", title="T", source_url=_URL)
    with pytest.raises(ExtractionFailedError):
        await YtdlpProvider().download(media, MediaFormat.AUDIO, Quality.AUDIO, tmp_path)


async def test_health_check_ok_and_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(b"2099.01.01", b"", 0))
    assert await YtdlpProvider().health_check() is ProviderHealth.OK
    _patch_proc(monkeypatch, _FakeProc(b"", b"boom", 1))
    assert await YtdlpProvider().health_check() is ProviderHealth.UNAVAILABLE


def test_format_selector_downloads_the_exact_offered_format_id() -> None:
    # The user was shown a 720p option backed by format_id "136"; the selector must
    # download exactly that format (so delivered quality + size match — #28/#29).
    media = MediaInfo(
        platform="youtube",
        video_id="v",
        title="T",
        source_url=_URL,
        formats=(
            MediaFormatOption(
                format=MediaFormat.VIDEO, quality=Quality.P720, provider_format_id="136"
            ),
            MediaFormatOption(
                format=MediaFormat.VIDEO, quality=Quality.P480, provider_format_id="135"
            ),
        ),
    )
    selector = _format_selector(media, MediaFormat.VIDEO, Quality.P720)
    assert selector == "136+bestaudio[acodec^=mp4a]/136+bestaudio/136"
    # A different tier resolves to its own format id.
    assert _format_selector(media, MediaFormat.VIDEO, Quality.P480).startswith("135+bestaudio")
    assert _format_selector(media, MediaFormat.AUDIO, Quality.MP3) == "bestaudio/best"


def test_format_selector_fallback_is_height_capped_never_uncapped() -> None:
    # No offered format id (stale/odd source): fall back to a height-capped selector that
    # can never deliver above the selected tier — the trailing uncapped `/best` is gone.
    media = MediaInfo(platform="youtube", video_id="v", title="T", source_url=_URL)
    selector = _format_selector(media, MediaFormat.VIDEO, Quality.P720)
    assert selector.startswith("bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]")
    assert "[height<=720]" in selector
    assert selector.endswith("best[height<=720]")  # capped fallback, not a bare /best
    assert "/best/" not in selector and not selector.endswith("/best")


def test_video_only_size_includes_audio_muxed_not_double_counted() -> None:
    provider = YtdlpProvider()
    info = provider._to_media_info(_URL, _INFO)
    # 137 is video-only (5000) + best audio (140 = 400) → 5400, not 5000.
    hd = next(o for o in info.formats if o.provider_format_id == "137")
    assert hd.approx_size_bytes == 5400
    # 18 is muxed (already contains audio) and has no reported size → no estimate.
    muxed = next(o for o in info.formats if o.provider_format_id == "18")
    assert muxed.approx_size_bytes is None


def test_muxed_only_source_still_offers_audio() -> None:
    """TikTok-style: only muxed formats, no audio-only stream — audio still offered."""
    muxed_only = {
        "id": "t",
        "title": "Clip",
        "duration": 30,
        "formats": [
            {"format_id": "mux", "vcodec": "h264", "acodec": "aac", "height": 720, "abr": 128},
        ],
    }
    info = YtdlpProvider()._to_media_info("https://www.tiktok.com/@a/video/1", muxed_only)
    audio = [o for o in info.formats if o.format is MediaFormat.AUDIO]
    assert len(audio) == 1  # a generic audio source the catalog expands from
    assert audio[0].provider_format_id is None  # downloaded via bestaudio/best
