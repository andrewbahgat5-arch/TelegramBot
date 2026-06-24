"""Unit tests for services.format_extraction (MASTER_PLAN Task 5.6)."""

from __future__ import annotations

from domain.entities.media import MediaFormatOption
from domain.enums import MediaFormat, Quality
from services.format_extraction import normalize_formats


def _vid(q: Quality, size: int | None = None, fid: str | None = None) -> MediaFormatOption:
    return MediaFormatOption(MediaFormat.VIDEO, q, size, fid)


def test_dedup_keeps_one_per_format_quality() -> None:
    options = [_vid(Quality.P720, 100), _vid(Quality.P720, 200)]
    result = normalize_formats(options)
    assert len(result) == 1


def test_dedup_prefers_concrete_then_larger() -> None:
    no_id = _vid(Quality.P720, 999, None)
    with_id = _vid(Quality.P720, 100, "137")
    assert normalize_formats([no_id, with_id])[0].provider_format_id == "137"


def test_sorts_video_before_audio_best_first() -> None:
    options = [
        MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 100, "a"),
        _vid(Quality.P480),
        _vid(Quality.P1080),
    ]
    result = normalize_formats(options)
    videos = [o for o in result if o.format is MediaFormat.VIDEO]
    audios = [o for o in result if o.format is MediaFormat.AUDIO]
    # Video group sorts best-first; the audio source expands to the codec catalog (D-041).
    assert [o.quality for o in videos] == [Quality.P1080, Quality.P480]
    assert len(audios) == 7
    assert result[0].format is MediaFormat.VIDEO and result[-1].format is MediaFormat.AUDIO


def test_empty_input() -> None:
    assert normalize_formats([]) == ()
