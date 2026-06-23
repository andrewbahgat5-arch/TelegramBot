"""YtdlpProvider — the sole V1 download provider (MASTER_PLAN 12.6.5, Task 5.3).

Wraps the ``yt-dlp`` binary as an async subprocess (no Python import of ``yt_dlp``;
this is the only module permitted to touch it — Section 12.6.9). Parses ``-J`` JSON
into a provider-agnostic :class:`MediaInfo`, maps vendor errors onto the domain
exceptions the registry interprets (Section 12.6.8), and implements ``health_check``.

Format extraction here is intentionally raw: it emits one option per usable yt-dlp
format. The provider-agnostic dedup/sort lives in ``services/format_extraction.py``
(Task 5.6) so it stays provider-independent.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import orjson

from core.logging import get_logger
from core.urls import detect_platform
from domain.entities.media import DownloadedFile, MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import (
    ExtractionFailedError,
    InfrastructureError,
    URLNotSupportedError,
)
from domain.protocols.downloader import (
    Capability,
    ProviderHealth,
    ProviderRetryElsewhere,
)

_log = get_logger("infrastructure.downloader.providers.ytdlp")

_DEFAULT_EXTRACT_TIMEOUT = 30.0
_DEFAULT_DOWNLOAD_TIMEOUT = 300.0
_DEFAULT_HEALTH_TIMEOUT = 10.0

# Quality tiers keyed by their standard *short* side (the "Np" label) and by their
# standard *long* side. Real pixel dimensions are matched to the nearest tier rather
# than floored: wide/portrait videos have non-16:9 dimensions (e.g. 4K = 3840x2026),
# so a floor on raw height mislabels every tier one step down.
_TIER_BY_SHORT_EDGE: tuple[tuple[int, Quality], ...] = (
    (2160, Quality.P2160),
    (1440, Quality.P1440),
    (1080, Quality.P1080),
    (720, Quality.P720),
    (480, Quality.P480),
    (360, Quality.P360),
    (240, Quality.P240),
    (144, Quality.P144),
)
_TIER_BY_LONG_EDGE: tuple[tuple[int, Quality], ...] = (
    (3840, Quality.P2160),
    (2560, Quality.P1440),
    (1920, Quality.P1080),
    (1280, Quality.P720),
    (854, Quality.P480),
    (640, Quality.P360),
    (426, Quality.P240),
    (256, Quality.P144),
)
# yt-dlp's own resolution label, e.g. "1080p", "2160p60", "1440p Premium".
_NOTE_TIER_RE = re.compile(r"(\d{3,4})\s*p")

# yt-dlp stderr fragments → how the registry should react.
_UNSUPPORTED_MARKERS = ("unsupported url", "is not a valid url")
_CONTENT_MARKERS = (
    "video unavailable",
    "private video",
    "this video is not available",
    "removed",
    "geo restricted",
    "sign in to confirm",
    "members-only",
)
_TRANSIENT_MARKERS = ("timed out", "temporary failure", "connection reset", "http error 5")


class YtdlpProvider:
    def __init__(
        self,
        ytdlp_path: str = "yt-dlp",
        *,
        extract_timeout: float = _DEFAULT_EXTRACT_TIMEOUT,
        download_timeout: float = _DEFAULT_DOWNLOAD_TIMEOUT,
    ) -> None:
        self.name = "ytdlp"
        self.supported_platforms = {"*"}
        self.capabilities = {Capability.VIDEO, Capability.AUDIO}
        self.priority = 100
        self._bin = ytdlp_path
        self._extract_timeout = extract_timeout
        self._download_timeout = download_timeout

    async def extract_info(self, url: str) -> MediaInfo:
        stdout = await self._run(
            [self._bin, "-J", "--no-playlist", "--no-warnings", url],
            timeout_s=self._extract_timeout,
        )
        try:
            info: dict[str, Any] = orjson.loads(stdout)
        except orjson.JSONDecodeError as exc:
            raise ExtractionFailedError("Could not parse media metadata.") from exc
        return self._to_media_info(url, info)

    async def download(
        self, media: MediaInfo, format_: MediaFormat, quality: Quality, dest: Path
    ) -> DownloadedFile:
        dest.mkdir(parents=True, exist_ok=True)
        selector = _format_selector(media, format_, quality)
        out_template = str(dest / f"{media.video_id}.%(ext)s")
        await self._run(
            [
                self._bin,
                "-f",
                selector,
                "--no-playlist",
                "--no-warnings",
                "-o",
                out_template,
                media.source_url,
            ],
            timeout_s=self._download_timeout,
        )
        produced = sorted(dest.glob(f"{media.video_id}.*"), key=lambda p: p.stat().st_size)
        if not produced:
            raise ExtractionFailedError("Download produced no file.")
        path = produced[-1]
        return DownloadedFile(
            path=path, size_bytes=path.stat().st_size, format=format_, quality=quality
        )

    async def health_check(self) -> ProviderHealth:
        try:
            await self._run([self._bin, "--version"], timeout_s=_DEFAULT_HEALTH_TIMEOUT)
        except Exception:
            return ProviderHealth.UNAVAILABLE
        return ProviderHealth.OK

    # --- subprocess + error mapping ---------------------------------------
    async def _run(self, args: list[str], *, timeout_s: float) -> bytes:
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (OSError, ValueError) as exc:  # binary missing / bad args
            raise InfrastructureError(f"yt-dlp could not be launched: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as exc:
            proc.kill()
            raise ProviderRetryElsewhere("yt-dlp timed out.") from exc

        if proc.returncode != 0:
            raise _map_error(stderr.decode(errors="replace"))
        return stdout

    def _to_media_info(self, url: str, info: dict[str, Any]) -> MediaInfo:
        platform = detect_platform(url)
        formats = tuple(_parse_formats(info.get("formats") or []))
        return MediaInfo(
            platform=platform,
            video_id=str(info.get("id") or ""),
            title=str(info.get("title") or "Untitled"),
            source_url=str(info.get("webpage_url") or url),
            duration=_opt_int(info.get("duration")),
            thumbnail_url=info.get("thumbnail"),
            formats=formats,
            raw=_curated_metadata(info),
        )


def _map_error(stderr: str) -> Exception:
    lowered = stderr.lower()
    if any(m in lowered for m in _UNSUPPORTED_MARKERS):
        return URLNotSupportedError("This URL is not supported.")
    if any(m in lowered for m in _CONTENT_MARKERS):
        return ExtractionFailedError("This content is unavailable.")
    if any(m in lowered for m in _TRANSIENT_MARKERS):
        return ProviderRetryElsewhere("Transient extractor error.")
    # Unknown non-zero exit: treat as a content/extraction failure (do not fail over
    # blindly — the registry stops on ExtractionFailedError, Section 12.6.8).
    return ExtractionFailedError("Extraction failed.")


def _parse_formats(raw_formats: list[dict[str, Any]]) -> list[MediaFormatOption]:
    options: list[MediaFormatOption] = []
    for fmt in raw_formats:
        format_id = fmt.get("format_id")
        if not format_id:
            continue
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        size = _opt_int(fmt.get("filesize") or fmt.get("filesize_approx"))
        height = _opt_int(fmt.get("height"))
        width = _opt_int(fmt.get("width"))
        if vcodec and vcodec != "none" and height:
            options.append(
                MediaFormatOption(
                    format=MediaFormat.VIDEO,
                    quality=_quality_for_format(width, height, fmt.get("format_note")),
                    approx_size_bytes=size,
                    provider_format_id=str(format_id),
                )
            )
        elif (not vcodec or vcodec == "none") and acodec and acodec != "none":
            options.append(
                MediaFormatOption(
                    format=MediaFormat.AUDIO,
                    quality=Quality.AUDIO,
                    approx_size_bytes=size,
                    provider_format_id=str(format_id),
                )
            )
    return options


def _quality_for_format(
    width: int | None, height: int | None, format_note: str | None
) -> Quality:
    """Resolve a display quality tier robustly across aspect ratios.

    Prefers yt-dlp's own ``format_note`` label (e.g. "2160p60"); otherwise snaps the
    format's longer edge to the nearest standard tier. Snapping to *nearest* (not a
    floor) is what fixes 4K on wide videos (3840x2026 → 2160p, not 1440p).
    """
    if format_note:
        match = _NOTE_TIER_RE.search(format_note)
        if match:
            return _nearest_tier(int(match.group(1)), _TIER_BY_SHORT_EDGE)
    if width and height:
        # Both edges known: the longer edge identifies the tier for any aspect ratio.
        return _nearest_tier(max(width, height), _TIER_BY_LONG_EDGE)
    if height:  # height-only: assume landscape, match the short-edge ladder
        return _nearest_tier(height, _TIER_BY_SHORT_EDGE)
    if width:
        return _nearest_tier(width, _TIER_BY_LONG_EDGE)
    return Quality.P144


def _nearest_tier(value: int, ladder: tuple[tuple[int, Quality], ...]) -> Quality:
    return min(ladder, key=lambda tier: abs(tier[0] - value))[1]


def _format_selector(media: MediaInfo, format_: MediaFormat, quality: Quality) -> str:
    for option in media.formats:
        if option.format is format_ and option.quality is quality and option.provider_format_id:
            return option.provider_format_id
    return "bestaudio/best" if format_ is MediaFormat.AUDIO else "bestvideo+bestaudio/best"


def _curated_metadata(info: dict[str, Any]) -> dict[str, Any]:
    keys = ("extractor", "uploader", "uploader_id", "view_count", "like_count", "webpage_url")
    return {k: info[k] for k in keys if info.get(k) is not None}


def _opt_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
