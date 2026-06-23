"""Unit tests for URLAnalyzerService (MASTER_PLAN Task 5.5, flow 16.1)."""

from __future__ import annotations

import pytest

from domain.entities.media import MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import URLNotSupportedError
from services.url_analyzer import URLAnalyzerService
from tests.unit._fakes import FakeMediaRepo, FakeProvider, make_cache_service

_URL = "https://example.org/clip"


def _provider_result() -> MediaInfo:
    return MediaInfo(
        platform="provider-says-x",  # overwritten by the analyzer's URL-derived value
        video_id="provider-id",
        title="A Clip",
        source_url=_URL,
        duration=100,
        formats=(
            MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 200, "a"),
            MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 100, "b"),  # dup → collapsed
            MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 50, "c"),
        ),
        raw={"uploader": "chan"},
    )


def _analyzer() -> tuple[URLAnalyzerService, FakeProvider, FakeMediaRepo]:
    downloader = FakeProvider("ytdlp", result=_provider_result())
    cache_service, _ = make_cache_service()
    repo = FakeMediaRepo()
    return URLAnalyzerService(downloader, cache_service, repo), downloader, repo


async def test_invalid_url_rejected() -> None:
    analyzer, downloader, _ = _analyzer()
    with pytest.raises(URLNotSupportedError):
        await analyzer.analyze("not a url")
    assert downloader.calls == 0


async def test_cache_miss_extracts_upserts_and_normalizes() -> None:
    analyzer, downloader, repo = _analyzer()
    result = await analyzer.analyze(_URL)
    assert downloader.calls == 1
    assert repo.upserts == 1
    assert result.media_id == 1
    # The two P720 video options were deduplicated to one (+ the audio option).
    assert len(result.info.formats) == 2
    # platform/video_id come from the URL, not the provider's claim.
    assert result.info.platform == "generic"


async def test_cache_hit_skips_extraction() -> None:
    analyzer, downloader, _ = _analyzer()
    first = await analyzer.analyze(_URL)
    second = await analyzer.analyze(_URL)
    assert downloader.calls == 1  # second call served from the metadata cache
    assert first.media_id == second.media_id


async def test_analyze_by_media_id_resolves_via_source_url() -> None:
    analyzer, _, repo = _analyzer()
    created = await analyzer.analyze(_URL)
    found = await analyzer.analyze_by_media_id(created.media_id)
    assert found is not None and found.media_id == created.media_id


async def test_analyze_by_unknown_media_id_returns_none() -> None:
    analyzer, _, _ = _analyzer()
    assert await analyzer.analyze_by_media_id(999) is None
