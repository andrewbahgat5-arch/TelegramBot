"""Unit tests for the Sprint 6 format carry-ins (MASTER_PLAN D-041, carry-in 3).

* Video size estimates include the muxed audio stream and pick a consistent codec.
* Audio expands into the explicit per-codec catalog whenever audio exists.
"""

from __future__ import annotations

from domain.entities.media import AUDIO_TARGETS, MediaFormatOption
from domain.enums import MediaFormat, Quality
from services.format_extraction import normalize_formats


def test_video_dedup_prefers_compatible_codec_and_preserves_size() -> None:
    raw = (
        # Two codecs for the same tier: av01 is larger but avc1 is preferred. Sizes
        # already include audio (computed in the provider); normalize keeps them as-is.
        MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 8_000_000, "v-av01", codec="av01"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 5_000_000, "v-avc1", codec="avc1"),
        MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 1_000_000, "a", codec="opus"),
    )
    result = normalize_formats(raw)
    video = next(o for o in result if o.format is MediaFormat.VIDEO)
    assert video.provider_format_id == "v-avc1"  # consistent, compatible codec
    assert video.approx_size_bytes == 5_000_000  # preserved, not re-augmented


def test_high_res_prefers_av01_over_vp9() -> None:
    # Above 1080p YouTube has no avc1, so the codec choice decides the 4K/1440p size.
    # AV1 is the more efficient (smaller) stream and must win over VP9 — this is what
    # kept our 2160p at ~1.4 GB (VP9) instead of the ~913 MB (AV1) shown elsewhere.
    raw = (
        MediaFormatOption(MediaFormat.VIDEO, Quality.P2160, 1_400_000_000, "v-vp9", codec="vp9"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P2160, 913_000_000, "v-av01", codec="av01"),
    )
    video = next(o for o in normalize_formats(raw) if o.format is MediaFormat.VIDEO)
    assert video.provider_format_id == "v-av01"
    assert video.approx_size_bytes == 913_000_000


def test_same_codec_tier_prefers_smaller_clean_stream() -> None:
    # A legacy muxed 360p (format 18) is bulkier than the clean DASH 360p of the same
    # codec; the smaller one must win so the displayed/downloaded size is the real one.
    raw = (
        MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 84_000_000, "18", codec="avc1"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 49_000_000, "134", codec="avc1"),
    )
    video = next(o for o in normalize_formats(raw) if o.format is MediaFormat.VIDEO)
    assert video.provider_format_id == "134"
    assert video.approx_size_bytes == 49_000_000


def test_known_size_beats_unknown_on_codec_tie() -> None:
    # Never trade a sized format for a sizeless placeholder of the same codec.
    raw = (
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, None, "sizeless", codec="avc1"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 60_000_000, "sized", codec="avc1"),
    )
    video = next(o for o in normalize_formats(raw) if o.format is MediaFormat.VIDEO)
    assert video.provider_format_id == "sized"


def test_audio_expands_into_per_codec_catalog() -> None:
    raw = (
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 4_000_000, "v", codec="avc1"),
        MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 1_000_000, "a-best", codec="opus"),
    )
    result = normalize_formats(raw)
    audio = [o for o in result if o.format is MediaFormat.AUDIO]

    assert {o.quality for o in audio} == {t.quality for t in AUDIO_TARGETS}
    # Each audio target points at the best source so the worker can transcode it.
    assert all(o.provider_format_id == "a-best" for o in audio)
    # Lossless targets are estimated larger than lossy ones.
    by_q = {o.quality: o.approx_size_bytes for o in audio}
    wav, mp3 = by_q[Quality.WAV], by_q[Quality.MP3]
    assert wav is not None and mp3 is not None
    assert wav > mp3


def test_no_audio_means_no_audio_options() -> None:
    raw = (MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 4_000_000, "v", codec="avc1"),)
    result = normalize_formats(raw)
    assert all(o.format is MediaFormat.VIDEO for o in result)


def test_video_tiers_sorted_high_to_low() -> None:
    raw = (
        MediaFormatOption(MediaFormat.VIDEO, Quality.P360, 1_000_000, "a", codec="avc1"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 5_000_000, "b", codec="avc1"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 3_000_000, "c", codec="avc1"),
    )
    result = normalize_formats(raw)
    qualities = [o.quality for o in result if o.format is MediaFormat.VIDEO]
    assert qualities == [Quality.P1080, Quality.P720, Quality.P360]
