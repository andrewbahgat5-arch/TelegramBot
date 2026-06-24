"""Provider-agnostic format post-processing (MASTER_PLAN Task 5.6 + Sprint 6 carry-in).

A provider's ``extract_info`` returns many raw format options (one per concrete
vendor format). ``normalize_formats`` turns them into the clean selection the user
sees:

* **Video** — one option per quality tier, picking a *consistent* codec per tier
  (compatibility order avc1 → vp9 → av01 → other) instead of the largest variant,
  and adding the best audio stream's size so the estimate reflects the final muxed
  file. This makes the displayed sizes sensible and roughly monotonic (carry-in 3).
* **Audio** — whenever the media has any audio stream, the explicit per-codec
  catalog (``AUDIO_TARGETS``: MP3/M4A/Opus/…; D-041) is offered. Each carries the
  best audio source's ``provider_format_id`` so the worker downloads that stream and
  FFmpeg transcodes/remuxes it to the chosen container.

Pure and provider-independent — it must never reference a vendor.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.entities.media import AUDIO_TARGETS, MediaFormatOption
from domain.enums import MediaFormat, Quality

# Display rank for a video quality tier (higher sorts first).
_QUALITY_RANK: dict[Quality, int] = {
    Quality.BEST: 9,
    Quality.P2160: 8,
    Quality.P1440: 7,
    Quality.P1080: 6,
    Quality.P720: 5,
    Quality.P480: 4,
    Quality.P360: 3,
    Quality.P240: 2,
    Quality.P144: 1,
}

# Preference order for a video codec family (lower = preferred). avc1/h264 first for
# broad device compatibility and predictable, smaller-per-tier sizes.
_CODEC_PREFERENCE: dict[str, int] = {"avc1": 0, "h264": 0, "vp9": 1, "av01": 2, "av1": 2}

# Rough multipliers applied to the best lossy audio size to estimate a lossless
# target's size (no source duration available here; labels are "~" approximations).
_LOSSLESS_SIZE_MULTIPLIER = 6


def normalize_formats(options: Iterable[MediaFormatOption]) -> tuple[MediaFormatOption, ...]:
    """Collapse video tiers (one consistent codec each) and expand audio per-codec.

    Video sizes already include audio and use a consistent estimate (computed in the
    provider, which has the bitrate/duration metadata), so this stage only dedupes and
    sorts video and expands the audio catalog (D-041) from the best audio source.
    """
    options = tuple(options)
    audio_sources = [o for o in options if o.format is MediaFormat.AUDIO]
    best_audio = _best_audio(audio_sources)

    videos = _dedupe_video(o for o in options if o.format is MediaFormat.VIDEO)
    audios = _audio_targets(best_audio) if audio_sources else []

    videos.sort(key=lambda o: -_QUALITY_RANK.get(o.quality, 0))
    return tuple(videos + audios)


def _dedupe_video(options: Iterable[MediaFormatOption]) -> list[MediaFormatOption]:
    best: dict[Quality, MediaFormatOption] = {}
    for option in options:
        incumbent = best.get(option.quality)
        if incumbent is None or _prefer_video(option, incumbent):
            best[option.quality] = option
    return list(best.values())


def _prefer_video(candidate: MediaFormatOption, incumbent: MediaFormatOption) -> bool:
    """Prefer a resolvable option, then a more compatible codec, then larger size."""
    if bool(candidate.provider_format_id) != bool(incumbent.provider_format_id):
        return bool(candidate.provider_format_id)
    cand_codec = _CODEC_PREFERENCE.get(candidate.codec or "", 99)
    inc_codec = _CODEC_PREFERENCE.get(incumbent.codec or "", 99)
    if cand_codec != inc_codec:
        return cand_codec < inc_codec
    return (candidate.approx_size_bytes or 0) > (incumbent.approx_size_bytes or 0)


def _best_audio(audio_sources: list[MediaFormatOption]) -> MediaFormatOption | None:
    if not audio_sources:
        return None
    return max(audio_sources, key=lambda o: o.approx_size_bytes or 0)


def _audio_targets(best_audio: MediaFormatOption | None) -> list[MediaFormatOption]:
    """One option per explicit codec target (D-041), pointing at the best source."""
    base_size = best_audio.approx_size_bytes if best_audio is not None else None
    provider_id = best_audio.provider_format_id if best_audio is not None else None
    out: list[MediaFormatOption] = []
    for target in AUDIO_TARGETS:
        size = _audio_target_size(base_size, lossless=target.lossless)
        out.append(
            MediaFormatOption(
                format=MediaFormat.AUDIO,
                quality=target.quality,
                approx_size_bytes=size,
                provider_format_id=provider_id,
                codec=target.container,
            )
        )
    return out


def _audio_target_size(base_size: int | None, *, lossless: bool) -> int | None:
    if base_size is None:
        return None
    return base_size * _LOSSLESS_SIZE_MULTIPLIER if lossless else base_size
