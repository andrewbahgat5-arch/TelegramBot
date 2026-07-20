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
from domain.exceptions import (
    AuthRequiredError,
    ExtractionFailedError,
    NoDownloadableMediaError,
    URLNotSupportedError,
    VideoUnavailableError,
)
from domain.protocols.downloader import ProviderHealth, ProviderRetryElsewhere
from infrastructure.downloader.providers.ytdlp_provider import (
    YtdlpProvider,
    _format_selector,
    _map_error,
    _parse_formats,
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


# The exact shape X/Twitter returns (captured from a real failing post, 2026-07-18):
# progressive http-* formats with a real height and filesize but NO codec fields, plus
# HLS duplicates we drop. Every X link produced zero options before the codec-state fix.
_X_FORMATS: list[dict[str, Any]] = [
    {"format_id": "hls-audio-128000-Audio", "protocol": "m3u8_native", "vcodec": "none",
     "acodec": None, "tbr": 128},
    {"format_id": "http-256", "protocol": "https", "vcodec": None, "acodec": None,
     "height": 270, "tbr": 256, "filesize": 1_272_768},
    {"format_id": "hls-105", "protocol": "m3u8_native", "vcodec": "avc1.4D4015",
     "acodec": "none", "height": 270, "tbr": 105.4},
    {"format_id": "http-832", "protocol": "https", "vcodec": None, "acodec": None,
     "height": 360, "tbr": 832, "filesize": 4_136_496},
    {"format_id": "http-2176", "protocol": "https", "vcodec": None, "acodec": None,
     "height": 718, "tbr": 2176, "filesize": 10_818_528},
]


def test_twitter_progressive_formats_without_codec_fields_are_kept() -> None:
    """REGRESSION: X reports no vcodec/acodec on its progressive mp4s. Treating an
    unreported codec as "absent" discarded all of them, so every X link failed with
    "no playable formats". A frame size means it is video, whatever the codec says."""
    options = _parse_formats(_X_FORMATS, duration=30)
    videos = [o for o in options if o.format is MediaFormat.VIDEO]
    assert [o.provider_format_id for o in videos] == ["http-256", "http-832", "http-2176"]
    # Real filesizes are used as-is: these are muxed, so audio must NOT be added on top.
    by_id = {o.provider_format_id: o for o in videos}
    assert by_id["http-2176"].approx_size_bytes == 10_818_528
    # Muxed-only source → an audio option is still offered (same rule as TikTok).
    assert any(o.format is MediaFormat.AUDIO for o in options)


def test_explicit_codec_none_still_excludes_storyboards() -> None:
    """The fix must not weaken the storyboard guard: yt-dlp's literal "none" is
    authoritative and keeps YouTube storyboards out."""
    storyboards = [
        {"format_id": "sb0", "protocol": "mhtml", "vcodec": "none", "acodec": "none",
         "height": 180},
    ]
    assert _parse_formats(storyboards, duration=100) == []


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


def test_video_less_post_on_a_social_platform_is_permanent_not_transient() -> None:
    """A text-only tweet reads fine but has nothing to download. Reporting that as
    "temporary, try again" sent users into retry loops on posts that can never work."""
    provider = YtdlpProvider()
    empty_tweet: dict[str, Any] = {
        "id": "1",
        "title": "just some text",
        "webpage_url": "https://x.com/u/status/1",
        "formats": [],
    }
    with pytest.raises(NoDownloadableMediaError):
        provider._to_media_info("https://x.com/u/status/1", empty_tweet)


def test_photo_post_on_a_social_platform_is_delivered_as_an_image() -> None:
    provider = YtdlpProvider()
    photo_tweet: dict[str, Any] = {
        "id": "2",
        "title": "a photo",
        "webpage_url": "https://x.com/u/status/2",
        "formats": [],
        "thumbnails": [{"url": "https://pbs.twimg.com/media/x.jpg", "width": 1200,
                        "height": 900}],
    }
    info = provider._to_media_info("https://x.com/u/status/2", photo_tweet)
    assert len(info.formats) == 1
    assert info.formats[0].format is MediaFormat.IMAGE


def test_map_error_carries_the_provider_reason_into_the_message() -> None:
    """error_logs stores the exception message; without the yt-dlp reason every row
    read "Extraction failed." and the cause was lost once container logs rotated."""
    err = _map_error("WARNING: something\nERROR: Requested content is not available\n")
    assert "Requested content is not available" in str(err)


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


def test_parse_formats_skips_hls_manifest_dupes_so_size_is_real() -> None:
    # YouTube lists an HLS 1080p (protocol m3u8, no filesize, inflated tbr) next to the
    # real DASH one. The HLS format must be dropped so the *displayed* size matches the
    # real download (bug: showed 475 MB from the bogus tbr estimate; real file was ~198).
    raw = [
        {"format_id": "96", "protocol": "m3u8_native", "vcodec": "avc1", "acodec": "none",
         "height": 1080, "tbr": 3393.0},  # no filesize → would estimate ~475 MB
        {"format_id": "137", "protocol": "https", "vcodec": "avc1", "acodec": "none",
         "height": 1080, "filesize": 179_000_000},
        {"format_id": "140", "protocol": "https", "vcodec": "none", "acodec": "mp4a",
         "filesize": 4_000_000},
    ]
    opts = _parse_formats(raw, duration=1176)
    videos = [o for o in opts if o.format is MediaFormat.VIDEO]
    assert [o.provider_format_id for o in videos] == ["137"]  # HLS 96 dropped
    # size = real 179 MB video + 4 MB audio, NOT the 475 MB tbr estimate
    assert 175_000_000 < (videos[0].approx_size_bytes or 0) < 190_000_000


async def test_extract_info_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_INFO), b"", 0))
    info = await YtdlpProvider().extract_info(_URL)
    assert info.video_id == "vid123"
    assert len(info.formats) == 3


_METADATA_ONLY: dict[str, Any] = {
    # What --ignore-no-formats-error yields when YouTube serves its bot-check wall:
    # rc=0, webpage metadata, ZERO formats — the reason exists only in stderr.
    "id": "2oPfC_Pwfu8",
    "title": "A documentary",
    "webpage_url": "https://www.youtube.com/watch?v=2oPfC_Pwfu8",
}


@pytest.mark.parametrize(
    "stderr",
    [
        b"WARNING: [youtube] 2oPfC_Pwfu8: Sign in to confirm you're not a bot.",
        # The apostrophe is a right-single-quote (U+2019) in real output — both must match.
        "WARNING: [youtube] Sign in to confirm you’re not a bot.".encode(),  # noqa: RUF001
    ],
)
async def test_extract_info_bot_check_wall_is_video_unavailable(
    monkeypatch: pytest.MonkeyPatch, stderr: bytes
) -> None:
    # rc=0 + metadata-only + the bot-check signature in stderr → the distinct
    # user-facing "this video needs verification" error, NOT "busy, try again"
    # (a retry cannot fix it — the egress IP is what's being challenged).
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_METADATA_ONLY), stderr, 0))
    with pytest.raises(VideoUnavailableError):
        await YtdlpProvider().extract_info(_URL)


async def test_youtube_extraction_uses_warp_only(monkeypatch: pytest.MonkeyPatch) -> None:
    # Metadata for a protected platform goes over WARP and nothing else — a failure
    # must not retry over the residential proxy (which YouTube walls) or DIRECT.
    seen: list[str] = []

    async def fake_exec(*args: Any, **_kw: Any) -> _FakeProc:
        seen.append(args[args.index("--proxy") + 1])
        return _FakeProc(b"", b"ERROR: HTTP Error 503", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    provider = YtdlpProvider(proxy="http://residential:1", warp_proxy="socks5://warp:1080")
    with pytest.raises(ProviderRetryElsewhere):
        await provider.extract_info(_URL)
    assert set(seen) == {"socks5://warp:1080"}  # never the residential proxy, never ""


async def test_extract_info_no_formats_without_bot_check_stays_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Metadata-only with no recognised wall signature keeps the existing transient
    # classification (the user is asked to try again).
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_METADATA_ONLY), b"", 0))
    with pytest.raises(ProviderRetryElsewhere):
        await YtdlpProvider().extract_info(_URL)


async def test_extract_info_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_proc(monkeypatch, _FakeProc(b"", b"ERROR: Unsupported URL: foo", 1))
    with pytest.raises(URLNotSupportedError):
        await YtdlpProvider().extract_info(_URL)


async def test_extract_info_null_json_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    """An extractor that matches but returns nothing prints a bare ``null`` and exits 0.

    Seen live on t.me links ("Extractor telegram:embed returned nothing"). ``null`` is
    valid JSON, so this used to reach ``_to_media_info`` as ``None`` and crash on
    ``None.get`` instead of surfacing a domain error.
    """
    _patch_proc(
        monkeypatch,
        _FakeProc(b"null", b"WARNING: Extractor telegram:embed returned nothing", 0),
    )
    with pytest.raises(URLNotSupportedError) as excinfo:
        await YtdlpProvider().extract_info("https://t.me/somechannel/1")
    assert "telegram:embed" in str(excinfo.value)


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


def _proxied_provider() -> YtdlpProvider:
    return YtdlpProvider(proxy="http://u:p@res.example:7577", warp_proxy="socks5://warp-lb:1080")


def _sized_media(size_bytes: int) -> MediaInfo:
    """Protected-platform media whose selected 720p option has a known size, so the
    size-based download split in routing.plan_egress is exercised end-to-end."""
    return MediaInfo(
        platform="youtube",
        video_id="vid",
        title="T",
        source_url=_URL,
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P720, size_bytes, "137"),),
    )


async def test_large_download_uses_residential_proxy_and_aria2c(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Over the 500 MB split → residential proxy first, on the fast aria2c path (WARP is
    # bandwidth-capped and cannot use aria2c).
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    media = _sized_media(900 * 1024 * 1024)
    await _proxied_provider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    args = captured["args"]
    assert "aria2c" in args and "--downloader" in args  # fast aria2c path
    assert "--proxy" in args and "http://u:p@res.example:7577" in args  # residential proxy


async def test_small_download_uses_warp_natively(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # At or under the split → WARP first, natively (SOCKS, so no aria2c).
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    media = _sized_media(20 * 1024 * 1024)
    await _proxied_provider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    args = captured["args"]
    assert "socks5://warp-lb:1080" in args
    assert "aria2c" not in args  # aria2c has no SOCKS support


async def test_large_download_falls_back_to_warp_native(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        calls.append(args)
        if len(calls) == 1:  # residential aria2c egress fails transiently
            return _FakeProc(b"", b"ERROR: aria2c exited with code 1", 1)
        (tmp_path / "vid.mp4").write_bytes(b"x" * 30)  # WARP native egress succeeds
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    media = _sized_media(900 * 1024 * 1024)
    result = await _proxied_provider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert result.size_bytes == 30 and len(calls) == 2
    assert "aria2c" in calls[0] and "http://u:p@res.example:7577" in calls[0]  # residential first
    # WARP fallback: native (no aria2c) via the WARP SOCKS proxy
    assert "aria2c" not in calls[1] and "socks5://warp-lb:1080" in calls[1]


async def test_small_download_falls_back_to_the_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The small-file branch keeps the other egress as its fallback too, so a failing
    # WARP pool never takes small downloads down entirely.
    calls: list[tuple[Any, ...]] = []

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        calls.append(args)
        if len(calls) == 1:  # WARP fails transiently
            return _FakeProc(b"", b"ERROR: HTTP Error 503", 1)
        (tmp_path / "vid.mp4").write_bytes(b"x" * 30)
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    media = _sized_media(20 * 1024 * 1024)
    result = await _proxied_provider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert result.size_bytes == 30 and len(calls) == 2
    assert "socks5://warp-lb:1080" in calls[0]  # WARP first
    assert "http://u:p@res.example:7577" in calls[1]  # residential proxy fallback


async def test_download_threshold_is_configurable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A deployment that lowers YTDLP_WARP_MAX_DOWNLOAD_MB sends the same file over the
    # proxy instead — no code change needed.
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    provider = YtdlpProvider(
        proxy="http://u:p@res.example:7577",
        warp_proxy="socks5://warp-lb:1080",
        warp_max_download_bytes=10 * 1024 * 1024,  # 10 MB split
    )
    media = _sized_media(20 * 1024 * 1024)
    await provider.download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    assert "http://u:p@res.example:7577" in captured["args"]


async def test_unprotected_platform_uses_direct_aria2c(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, tuple[Any, ...]] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        return _FakeProc(b"", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    (tmp_path / "vid.mp4").write_bytes(b"x" * 10)
    # tiktok is NOT protected → DIRECT egress (no proxy), still fast via aria2c.
    media = MediaInfo(platform="tiktok", video_id="vid", title="T", source_url=_URL)
    await _proxied_provider().download(media, MediaFormat.VIDEO, Quality.P720, tmp_path)
    args = captured["args"]
    assert "aria2c" in args  # DIRECT still uses aria2c (HTTP, no proxy)
    assert "http://u:p@res.example:7577" not in args  # residential proxy NOT spent here
    # DIRECT is expressed as an empty --proxy value (forces the server's own IP)
    idx = args.index("--proxy")
    assert args[idx + 1] == ""


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


# --- auth-required classification ----------------------------------------
# Real yt-dlp stderr, captured from production (2026-07-19) and the extractors' source.
_INSTAGRAM_EMPTY_RESPONSE = (
    "WARNING: [Instagram] C8QltIDSLNc: No CSRF token set by Instagram API\n"
    "ERROR: [Instagram] C8QltIDSLNc: Instagram sent an empty media response. Check if "
    "this post is accessible in your browser without being logged-in. If it is not, "
    "then use --cookies-from-browser or --cookies for the authentication."
)


@pytest.mark.parametrize(
    "stderr",
    [
        _INSTAGRAM_EMPTY_RESPONSE,
        "ERROR: [Instagram] x: Requested content is not available, rate-limit reached "
        "or login required",
        "ERROR: [facebook] 123: This video is only available for registered users",
        "ERROR: [youtube] x: Sign in to confirm your age. This video may be "
        "age-restricted",
        "ERROR: [instagram] x: This post is private",
    ],
)
def test_login_walled_content_maps_to_auth_required(stderr: str) -> None:
    """A login wall must reach the user as "you need an account", not a generic
    extraction failure — retrying, failing over or swapping cookies cannot help,
    because we hold no session for these platforms by design."""
    assert isinstance(_map_error(stderr), AuthRequiredError)


def test_auth_required_takes_priority_over_the_rate_limit_marker() -> None:
    """Instagram's wording mentions BOTH ("rate-limit reached or login required").
    Classifying it transient would promise "try again later" on a post that can never
    work anonymously, so auth wins."""
    err = _map_error("ERROR: Requested content is not available, rate-limit reached or "
                     "login required")
    assert isinstance(err, AuthRequiredError)
    assert not isinstance(err, ProviderRetryElsewhere)


def test_bot_check_wall_is_not_misread_as_auth_required() -> None:
    """YouTube's "sign in to confirm you're not a bot" is the anti-bot wall — a route
    problem that a retry/egress failover fixes. Only "sign in to confirm your AGE" is
    an auth wall. The markers list spells both out so the prefix cannot collide."""
    err = _map_error("ERROR: Sign in to confirm you're not a bot")
    assert isinstance(err, ProviderRetryElsewhere)
    assert not isinstance(err, AuthRequiredError)


def test_auth_required_message_keeps_the_provider_reason() -> None:
    err = _map_error(_INSTAGRAM_EMPTY_RESPONSE)
    assert "empty media response" in str(err)


async def test_extract_info_auth_wall_with_zero_exit_is_auth_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--ignore-no-formats-error makes a login-walled post exit 0 with empty formats —
    the same shape as a text-only tweet, so _map_error never sees it. Without reading
    stderr here the user got "nothing downloadable" on a post that is merely private."""
    walled: dict[str, Any] = {
        "id": "C8QltIDSLNc",
        "title": "Instagram post",
        "webpage_url": "https://www.instagram.com/reel/C8QltIDSLNc/",
        "formats": [],
    }
    _patch_proc(
        monkeypatch,
        _FakeProc(orjson.dumps(walled), _INSTAGRAM_EMPTY_RESPONSE.encode(), 0),
    )
    with pytest.raises(AuthRequiredError):
        await YtdlpProvider().extract_info("https://www.instagram.com/reel/C8QltIDSLNc/")


async def test_extract_info_empty_post_without_auth_signal_stays_no_media(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counterpart: a genuinely empty post must NOT be relabelled auth-required."""
    empty: dict[str, Any] = {
        "id": "1",
        "title": "just text",
        "webpage_url": "https://x.com/u/status/1",
        "formats": [],
    }
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(empty), b"", 0))
    with pytest.raises(NoDownloadableMediaError):
        await YtdlpProvider().extract_info("https://x.com/u/status/1")


# --- multi-item posts (Instagram carousels) --------------------------------
# Shape captured from the live post instagram.com/p/DavxiQsHKB0/ (2026-07-19): the
# post is a PLAYLIST with no formats of its own; the media is in `entries`.
def _carousel(n: int = 3) -> dict[str, Any]:
    return {
        "_type": "playlist",
        "id": "DavxiQsHKB0",
        "title": "Post by fifaworldcup",
        "formats": [],
        "entries": [
            {
                "id": f"item{i}",
                "title": f"Video {i} by fifaworldcup",
                "webpage_url": "https://www.instagram.com/p/DavxiQsHKB0/",
                # Real Instagram entries carry a per-slide thumbnail; the gallery is a
                # photo message, so a missing preview is a visible defect.
                "thumbnail": f"https://cdn.example/thumb{i}.jpg",
                "formats": [
                    {"format_id": f"v{i}", "ext": "mp4", "height": 720,
                     "vcodec": "avc1", "acodec": "mp4a", "filesize": 1_000_000},
                ],
            }
            for i in range(1, n + 1)
        ],
    }


_CAROUSEL_URL = "https://www.instagram.com/p/DavxiQsHKB0/"


async def test_carousel_without_an_index_returns_the_item_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION: a carousel's media lives in `entries` and the post itself has NO
    formats. Reading only the top level made a public post holding five 1440p videos
    surface to the user as "no downloadable media"."""
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_carousel(5)), b"", 0))
    info = await YtdlpProvider().extract_info(_CAROUSEL_URL)
    assert len(info.carousel_items) == 5
    assert info.formats == ()  # nothing chosen yet
    assert [i.index for i in info.carousel_items] == [1, 2, 3, 4, 5]
    assert all(i.kind is MediaFormat.VIDEO for i in info.carousel_items)
    # Every item must carry a preview or the gallery renders an empty photo.
    assert all(i.thumbnail_url for i in info.carousel_items)


async def test_carousel_item_index_selects_that_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_carousel(3)), b"", 0))
    info = await YtdlpProvider().extract_info(_CAROUSEL_URL, item_index=2)
    assert info.carousel_index == 2
    assert info.carousel_items == ()  # this IS an item, not the index
    assert info.formats  # the entry's formats came through
    # Its identity must differ from its siblings or they collide in the cache/DB.
    assert info.video_id.endswith("#2")


async def test_carousel_item_ids_are_distinct_per_slide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two slides must never share a video_id — that key is the metadata row AND the
    file_id cache, so a collision would serve slide 1's file for slide 3."""
    ids = set()
    for n in (1, 2, 3):
        _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_carousel(3)), b"", 0))
        info = await YtdlpProvider().extract_info(_CAROUSEL_URL, item_index=n)
        ids.add(info.video_id)
    assert len(ids) == 3


async def test_single_entry_post_skips_the_picker(monkeypatch: pytest.MonkeyPatch) -> None:
    """One entry is not a choice — flatten straight to it rather than asking."""
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_carousel(1)), b"", 0))
    info = await YtdlpProvider().extract_info(_CAROUSEL_URL)
    assert info.carousel_items == ()
    assert info.formats


async def test_carousel_out_of_range_index_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(_carousel(3)), b"", 0))
    with pytest.raises(URLNotSupportedError):
        await YtdlpProvider().extract_info(_CAROUSEL_URL, item_index=9)


def test_carousel_label_height_matches_what_is_actually_offered() -> None:
    """The picker label must come from the SAME parser that builds the options.

    Reading raw entry heights advertised 1440p on a post whose real best option was
    480p — the button promised a quality that was not on the next screen.
    """
    from infrastructure.downloader.providers.ytdlp_provider import (
        _best_entry_height,
        _entry_options,
    )

    entry = {
        "formats": [
            # An HLS duplicate claiming 1440p, which _parse_formats drops.
            {"format_id": "hls-1", "protocol": "m3u8_native", "height": 1440,
             "vcodec": "avc1", "acodec": "none"},
            {"format_id": "v1", "ext": "mp4", "height": 480, "vcodec": "avc1",
             "acodec": "mp4a", "filesize": 500_000},
        ]
    }
    offered = {o.quality.value for o in _entry_options(entry) if o.format is MediaFormat.VIDEO}
    assert _best_entry_height(entry) == 480
    assert "1440p" not in offered


# --- portrait tiers + bitrate selection (Instagram quality regression) ------
@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        # Instagram portrait, measured live 2026-07-19. The long-edge ladder demoted
        # every one of these by a tier or two, so the offered quality was far below
        # what the source actually had.
        (1080, 1440, Quality.P1080),
        (720, 960, Quality.P720),
        (540, 720, Quality.P480),
        (1080, 1920, Quality.P1080),  # Shorts/Reels
        # Landscape must be unchanged, including the wide-4K case the nearest-tier
        # snapping was originally introduced for.
        (1920, 1080, Quality.P1080),
        (1280, 720, Quality.P720),
        (3840, 2160, Quality.P2160),
        (3840, 2026, Quality.P2160),
    ],
)
def test_quality_tier_is_named_by_the_short_edge(
    width: int, height: int, expected: Quality
) -> None:
    """A video is named by its short edge in every orientation: 1920x1080 and
    1080x1920 are both 1080p."""
    assert _quality_for_format(width, height, None) is expected


def test_highest_bitrate_wins_at_an_identical_tier() -> None:
    """REGRESSION: Instagram ships six 720x960 VP9 rungs (220k…815k) and reports no
    filesize for any. The "prefer smaller" tie-break therefore kept the 220k stream and
    the delivered video looked visibly bad. At an equal tier and codec, bitrate decides.
    """
    from services.format_extraction import normalize_formats

    rungs = [
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, None, f"dash-{br}", "vp09",
                          bitrate_kbps=br)
        for br in (220.8, 232.1, 299.9, 421.7, 557.4, 815.0)
    ]
    out = [o for o in normalize_formats(rungs) if o.format is MediaFormat.VIDEO]
    assert len(out) == 1  # one option per tier
    assert out[0].provider_format_id == "dash-815.0"


def test_bitrate_tiebreak_does_not_disturb_the_format_18_case() -> None:
    """The oversized legacy muxed 360p must still lose to the clean DASH one when no
    bitrate is reported — that rule is what keeps displayed sizes honest."""
    from services.format_extraction import normalize_formats

    muxed = MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 9_000_000, "18", "avc1")
    dash = MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 2_000_000, "134", "avc1")
    out = [o for o in normalize_formats([muxed, dash]) if o.format is MediaFormat.VIDEO]
    assert out[0].provider_format_id == "134"


# --- YouTube playlists -----------------------------------------------------
def test_playlist_urls_are_told_apart_from_single_videos() -> None:
    """A `watch?v=…&list=…` link means "this video, which happens to be in a list" —
    expanding it into the whole playlist would be the opposite of what was asked."""
    from infrastructure.downloader.providers.ytdlp_provider import _is_playlist_url

    for playlist in (
        "https://www.youtube.com/playlist?list=PLBCF2DAC6FFB574DE",
        "https://www.youtube.com/@someuser",
        "https://www.youtube.com/channel/UCabc",
    ):
        assert _is_playlist_url(playlist), playlist
    for single in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz",  # video first
        "https://www.instagram.com/p/DavxiQsHKB0/",
    ):
        assert not _is_playlist_url(single), single


def test_flat_playlist_entry_is_treated_as_video_not_image() -> None:
    """REGRESSION: a flat playlist entry has NO formats, so the kind heuristic fell
    through to IMAGE and every playlist rendered as a wall of "Download Image". An
    entry with its own video url is a video we simply have not extracted yet."""
    from infrastructure.downloader.providers.ytdlp_provider import _entry_kind

    flat = {"id": "abc123", "ie_key": "Youtube", "title": "A video", "formats": []}
    assert _entry_kind(flat) is MediaFormat.VIDEO
    # Something with neither formats nor its own url is still an image/unknown.
    assert _entry_kind({"id": "x", "formats": []}) is MediaFormat.IMAGE


def test_playlist_entry_resolves_to_its_own_url() -> None:
    from infrastructure.downloader.providers.ytdlp_provider import _entry_own_url

    assert _entry_own_url({"id": "abc", "ie_key": "Youtube"}) == (
        "https://www.youtube.com/watch?v=abc"
    )
    assert _entry_own_url({"webpage_url": "https://x.test/v/1"}) == "https://x.test/v/1"
    # A carousel slide has no url of its own — it must NOT be re-extracted, it is
    # flattened and addressed by --playlist-items instead.
    assert _entry_own_url({"id": "slide", "formats": [{"format_id": "0"}]}) is None


async def test_playlist_listing_is_capped_and_reports_the_real_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A playlist can hold thousands. Showing the first N is fine; pretending that is
    all there is, is not — the caption says "showing 50 of 200"."""
    from infrastructure.downloader.providers.ytdlp_provider import MAX_PLAYLIST_ITEMS

    big = {
        "_type": "playlist",
        "id": "PL1",
        "title": "Huge playlist",
        "formats": [],
        "entries": [
            {"id": f"vid{i}", "ie_key": "Youtube", "title": f"Video {i}", "formats": []}
            for i in range(200)
        ],
    }
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(big), b"", 0))
    info = await YtdlpProvider().extract_info(
        "https://www.youtube.com/playlist?list=PL1"
    )
    assert len(info.carousel_items) == MAX_PLAYLIST_ITEMS == 50
    assert info.raw["playlist_total"] == 200  # the note needs the real number
    assert all(i.kind is MediaFormat.VIDEO for i in info.carousel_items)


async def test_playlist_items_offer_audio_even_though_flat_entries_have_no_formats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REGRESSION: a flat playlist entry has no inline formats, so audio-detection
    returned False and the gallery hid the Audio button — a music playlist offered no
    way to download the song. A YouTube video always has audio; assume it present until
    the item is actually extracted."""
    playlist = {
        "_type": "playlist",
        "id": "PL1",
        "title": "Songs",
        "formats": [],
        "entries": [
            {"id": "aaa", "ie_key": "Youtube", "title": "Song A", "formats": []},
            {"id": "bbb", "ie_key": "Youtube", "title": None, "formats": []},  # sparse
        ],
    }
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(playlist), b"", 0))
    info = await YtdlpProvider().extract_info("https://www.youtube.com/playlist?list=PL1")
    assert all(i.has_audio for i in info.carousel_items)  # audio button will show
    # A carousel slide (inline formats, video-only) must STILL be gated off.
    from infrastructure.downloader.providers.ytdlp_provider import _entry_has_audio
    video_only_slide = {"formats": [{"format_id": "0", "vcodec": "avc1", "acodec": "none",
                                     "height": 720}]}
    assert _entry_has_audio(video_only_slide) is False


def test_titleless_playlist_entry_falls_back_to_the_video_id() -> None:
    """A sparse flat entry (no title) should show its video id, not a meaningless
    "Item N" — the real title is filled in on selection."""
    from infrastructure.downloader.providers.ytdlp_provider import _entry_title
    assert _entry_title({"id": "fIc_VEQ7Vo0", "title": None}, 2) == "Video 2 (fIc_VEQ7Vo0)"
    assert _entry_title({"id": "x", "title": "Real Title"}, 3) == "Real Title"
    assert _entry_title({"title": None}, 5) == "Item 5"  # truly nothing


async def test_playlist_item_carries_its_own_url_for_direct_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A playlist entry exposes item_url so selecting it can analyze that video
    DIRECTLY (fast, single-video) — the earlier flow re-ran the whole playlist on the
    Video click, which timed out and made the button do nothing. A carousel slide, which
    has no url of its own, keeps item_url = None (it is addressed by --playlist-items)."""
    # Two entries so extract_info returns the INDEX (the item list) rather than
    # auto-selecting a lone item — we only need to check how the browse rows are built.
    playlist = {
        "_type": "playlist", "id": "PL1", "title": "Songs", "formats": [],
        "entries": [
            {"id": "vvv", "ie_key": "Youtube", "title": "Song A", "formats": []},
            {"id": "www", "ie_key": "Youtube", "title": "Song B", "formats": []},
        ],
    }
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(playlist), b"", 0))
    info = await YtdlpProvider().extract_info("https://www.youtube.com/playlist?list=PL1")
    assert info.carousel_items[0].item_url == "https://www.youtube.com/watch?v=vvv"

    carousel = {
        "_type": "playlist", "id": "IGPOST", "title": "Post", "formats": [],
        "entries": [
            {"id": "s1", "webpage_url": "https://www.instagram.com/p/IGPOST/",
             "formats": [{"format_id": "0", "vcodec": "avc1", "acodec": "mp4a", "height": 720}]},
            {"id": "s2", "webpage_url": "https://www.instagram.com/p/IGPOST/",
             "formats": [{"format_id": "0", "vcodec": "avc1", "acodec": "mp4a", "height": 720}]},
        ],
    }
    _patch_proc(monkeypatch, _FakeProc(orjson.dumps(carousel), b"", 0))
    ig = await YtdlpProvider().extract_info("https://www.instagram.com/p/IGPOST/")
    # The slide's webpage_url equals the POST url, so it is NOT a distinct own url —
    # it must be addressed by --playlist-items, not re-analyzed on its own.
    assert ig.carousel_items[0].item_url == "https://www.instagram.com/p/IGPOST/"
