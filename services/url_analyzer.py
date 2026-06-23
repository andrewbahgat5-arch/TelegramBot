"""URLAnalyzerService (MASTER_PLAN Component 9.2, Task 5.5, flow 16.1).

Turns a user URL into an :class:`AnalyzedMedia` (the DB ``media_id`` plus a
provider-agnostic :class:`MediaInfo`). Validates and normalizes the URL, derives
``(platform, video_id)``, checks the metadata cache, and on a miss calls the
``DownloaderRegistry`` (never a provider directly), normalizes the formats, UPSERTs
``media_metadata`` with a COALESCE merge (D-011), and writes the cache.

The ``(platform, video_id)`` used for the DB row and cache key is derived from the
URL alone (``core.urls``) so the pre-extraction cache lookup and the post-extraction
UPSERT address the same row.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from core.urls import detect_platform, extract_video_id, is_valid_url, normalize_url
from domain.entities.media import MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import URLNotSupportedError
from domain.protocols.downloader import DownloaderProtocol
from domain.protocols.repositories import MediaRepositoryProtocol
from services.cache_service import CacheService
from services.format_extraction import normalize_formats


@dataclass(frozen=True, slots=True)
class AnalyzedMedia:
    """Result of :meth:`URLAnalyzerService.analyze`: the DB id + discovered info."""

    media_id: int
    info: MediaInfo


class URLAnalyzerService:
    def __init__(
        self,
        downloader: DownloaderProtocol,
        cache: CacheService,
        media_repo: MediaRepositoryProtocol[Any],
    ) -> None:
        self._downloader = downloader
        self._cache = cache
        self._media_repo = media_repo

    async def analyze(self, url: str) -> AnalyzedMedia:
        if not is_valid_url(url):
            raise URLNotSupportedError("That doesn't look like a valid link.")

        normalized = normalize_url(url)
        platform = detect_platform(normalized)
        video_id = extract_video_id(normalized, platform)

        cached = await self._cache.get_metadata(platform, video_id)
        if cached is not None:
            return _from_cache(cached)

        extracted = await self._downloader.extract_info(normalized)
        info = dataclasses.replace(
            extracted,
            platform=platform,
            video_id=video_id,
            formats=normalize_formats(extracted.formats),
        )

        row = await self._media_repo.upsert_metadata(
            platform=platform,
            video_id=video_id,
            title=info.title,
            source_url=info.source_url,
            duration=info.duration,
            thumbnail_url=info.thumbnail_url,
            metadata_json=info.raw,
        )
        await self._cache.set_metadata(platform, video_id, _to_cache(row.id, info))
        return AnalyzedMedia(media_id=row.id, info=info)

    async def analyze_by_media_id(self, media_id: int) -> AnalyzedMedia | None:
        """Re-resolve a previously analyzed media by its DB id (callback step).

        Looks up the stored ``source_url`` and re-runs :meth:`analyze` (which serves
        from the metadata cache on a hit, re-extracting only if it expired). Returns
        None if the media row no longer exists.
        """
        row = await self._media_repo.get_by_id(media_id)
        if row is None:
            return None
        return await self.analyze(row.source_url)


def _to_cache(media_id: int, info: MediaInfo) -> dict[str, Any]:
    return {
        "media_id": media_id,
        "platform": info.platform,
        "video_id": info.video_id,
        "title": info.title,
        "source_url": info.source_url,
        "duration": info.duration,
        "thumbnail_url": info.thumbnail_url,
        "formats": [
            {
                "format": o.format.value,
                "quality": o.quality.value,
                "approx_size_bytes": o.approx_size_bytes,
                "provider_format_id": o.provider_format_id,
            }
            for o in info.formats
        ],
        "raw": info.raw,
    }


def _from_cache(data: dict[str, Any]) -> AnalyzedMedia:
    formats = tuple(
        MediaFormatOption(
            format=MediaFormat(o["format"]),
            quality=Quality(o["quality"]),
            approx_size_bytes=o["approx_size_bytes"],
            provider_format_id=o["provider_format_id"],
        )
        for o in data["formats"]
    )
    info = MediaInfo(
        platform=data["platform"],
        video_id=data["video_id"],
        title=data["title"],
        source_url=data["source_url"],
        duration=data["duration"],
        thumbnail_url=data["thumbnail_url"],
        formats=formats,
        raw=data["raw"],
    )
    return AnalyzedMedia(media_id=data["media_id"], info=info)
