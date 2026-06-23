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
        ("ERROR: HTTP Error 503", ProviderRetryElsewhere),
        ("ERROR: something weird", ExtractionFailedError),
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


def test_format_selector_prefers_known_id_else_falls_back() -> None:
    media = MediaInfo(
        platform="youtube",
        video_id="v",
        title="T",
        source_url=_URL,
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, None, "137"),),
    )
    assert _format_selector(media, MediaFormat.VIDEO, Quality.P720) == "137"
    assert _format_selector(media, MediaFormat.AUDIO, Quality.AUDIO) == "bestaudio/best"
