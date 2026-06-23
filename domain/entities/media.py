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
