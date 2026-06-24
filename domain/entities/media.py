"""Media value objects (MASTER_PLAN 12.6.2, Sprint 5).

Framework-free, immutable objects that cross the provider→service→bot boundary:

* :class:`MediaFormatOption` — one selectable (format, quality) the user may pick.
* :class:`MediaInfo` — the result of ``DownloaderProtocol.extract_info``: the
  metadata plus the available format options.
* :class:`DownloadedFile` — the result of ``DownloaderProtocol.download``.

These carry no I/O and no framework imports (Section 8). ``MediaInfo.raw`` holds the
provider's full metadata blob, merged into ``media_metadata.metadata_json`` via
COALESCE (D-011).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from domain.enums import MediaFormat, Quality


@dataclass(frozen=True, slots=True)
class MediaFormatOption:
    """One user-selectable download option discovered for a piece of media."""

    format: MediaFormat
    quality: Quality
    approx_size_bytes: int | None = None
    # The provider's concrete format selector (e.g. a yt-dlp format id), opaque to
    # every layer above the provider. Used by ``download`` to reproduce the choice.
    provider_format_id: str | None = None
    # Descriptive, provider-agnostic codec family (e.g. "avc1", "vp9", "opus") — D-041.
    # Used for consistent per-tier video selection and for audio remux/transcode hints.
    codec: str | None = None


@dataclass(frozen=True, slots=True)
class AudioTarget:
    """A selectable audio output (D-041): the codec/container the user may request.

    ``ffmpeg_codec`` is the FFmpeg encoder (``-c:a``); ``container`` is the output
    file extension. ``native_acodecs`` lists source codecs that already match the
    container, so they may be remuxed (``-c:a copy``) instead of re-encoded.
    """

    quality: Quality
    label: str
    container: str
    ffmpeg_codec: str
    native_acodecs: tuple[str, ...] = ()
    lossless: bool = False


# Fixed catalog of audio targets offered whenever a media has any audio stream
# (D-041). Order is the display order in the quality keyboard.
AUDIO_TARGETS: tuple[AudioTarget, ...] = (
    AudioTarget(Quality.MP3, "MP3", "mp3", "libmp3lame", native_acodecs=("mp3",)),
    AudioTarget(Quality.M4A, "M4A (AAC)", "m4a", "aac", native_acodecs=("aac", "mp4a")),
    AudioTarget(Quality.OPUS, "Opus", "opus", "libopus", native_acodecs=("opus",)),
    AudioTarget(Quality.OGG, "OGG (Vorbis)", "ogg", "libvorbis", native_acodecs=("vorbis",)),
    AudioTarget(Quality.AAC, "AAC", "aac", "aac", native_acodecs=("aac", "mp4a")),
    AudioTarget(Quality.WAV, "WAV (lossless)", "wav", "pcm_s16le", lossless=True),
    AudioTarget(Quality.FLAC, "FLAC (lossless)", "flac", "flac", lossless=True),
)

AUDIO_TARGET_BY_QUALITY: dict[Quality, AudioTarget] = {t.quality: t for t in AUDIO_TARGETS}


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Discovered metadata + available formats for a URL (provider-agnostic)."""

    platform: str
    video_id: str
    title: str
    source_url: str
    duration: int | None = None
    thumbnail_url: str | None = None
    formats: tuple[MediaFormatOption, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    """A produced local file ready for upload to Telegram."""

    path: Path
    size_bytes: int
    format: MediaFormat
    quality: Quality
