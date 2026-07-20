"""Provider-agnostic format post-processing (MASTER_PLAN Task 5.6 + Sprint 6 carry-in).

A provider's ``extract_info`` returns many raw format options (one per concrete
vendor format). ``normalize_formats`` turns them into the clean selection the user
sees:

* **Video** — one option per quality tier, picking a *consistent* codec per tier
  (order avc1 → av01 → vp9 → other) instead of the largest variant, and adding the
  best audio stream's size so the estimate reflects the final muxed
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
# broad device compatibility (and it's all YouTube offers at ≤1080p). Above 1080p there
# is no avc1, so the next choice decides the high-res size: av01 (AV1) before vp9, because
# AV1 is markedly more efficient — a 4K/1440p AV1 stream is ~30-40% smaller than the VP9
# one for the same tier, which is why picking vp9 made our 2160p/1440p sizes far larger
# than they need to be. (The exact chosen format is also what gets downloaded, so display
# and delivery stay in step — D-046.)
_CODEC_PREFERENCE: dict[str, int] = {"avc1": 0, "h264": 0, "av01": 1, "av1": 1, "vp9": 2}

# Effective bitrate (kbps) each lossy target lands at under FFmpeg's default encoder
# settings (the transcoder sets no explicit -b:a). Calibrated against real
# YouTube→FFmpeg outputs (2026-07); close estimates, not guarantees. Sizing every
# lossy target off one "best source size" was the bug — Opus/OGG re-encode much
# smaller than the AAC source, so they read too large.
_TARGET_KBPS: dict[Quality, int] = {
    Quality.MP3: 128,
    Quality.M4A: 128,
    Quality.AAC: 128,
    Quality.OPUS: 88,
    Quality.OGG: 96,
}
# Lossless sizing. WAV is raw PCM = asr*channels*bytes*duration; FLAC of a lossy source
# (all YouTube gives us) only compresses ~10%. The old flat x6 was badly wrong (a 200 MB
# WAV read as 100 MB). ``asr``/``channels`` default to YouTube's best (opus) audio.
_PCM_BYTES_PER_SAMPLE = 2  # pcm_s16le (16-bit)
_FLAC_FRACTION_OF_PCM = 0.9
_DEFAULT_ASR = 48000
_DEFAULT_CHANNELS = 2
# Fallback multiplier only when duration is unknown, so lossless still sorts last.
_LOSSLESS_SIZE_MULTIPLIER = 6


def normalize_formats(
    options: Iterable[MediaFormatOption], *, duration: int | None = None
) -> tuple[MediaFormatOption, ...]:
    """Collapse video tiers (one consistent codec each) and expand audio per-codec.

    Video sizes already include audio and use a consistent estimate (computed in the
    provider, which has the bitrate/duration metadata), so this stage only dedupes and
    sorts video and expands the audio catalog (D-041). Each audio target is sized for how
    the worker actually produces it (per-codec bitrate / PCM), which needs ``duration``.
    """
    options = tuple(options)
    audio_sources = [o for o in options if o.format is MediaFormat.AUDIO]

    # Image options carry no tiers/codecs to normalize — pass them through untouched.
    images = [o for o in options if o.format is MediaFormat.IMAGE]
    videos = _dedupe_video(o for o in options if o.format is MediaFormat.VIDEO)
    audios = _audio_targets(audio_sources, duration) if audio_sources else []

    videos.sort(key=lambda o: -_QUALITY_RANK.get(o.quality, 0))
    return tuple(images + videos + audios)


def _dedupe_video(options: Iterable[MediaFormatOption]) -> list[MediaFormatOption]:
    best: dict[Quality, MediaFormatOption] = {}
    for option in options:
        incumbent = best.get(option.quality)
        if incumbent is None or _prefer_video(option, incumbent):
            best[option.quality] = option
    return list(best.values())


def _prefer_video(candidate: MediaFormatOption, incumbent: MediaFormatOption) -> bool:
    """Prefer a resolvable option, then a more compatible/efficient codec, then a known
    size, then the *smaller* file.

    Preferring smaller on a codec tie picks the clean DASH stream over a legacy muxed
    one (e.g. YouTube's format 18: an oversized 360p that otherwise won the old
    larger-wins tie-break and displayed/downloaded far bigger than the real thing).
    A known size always beats an unknown one so we never trade a sized format for a
    sizeless placeholder.

    BEFORE the size comparison, an identical codec at the same tier is settled by
    BITRATE, highest wins. Sources publish several rungs at one resolution — Instagram
    ships six 720x960 VP9 streams from 220k to 815k and reports no filesize for any of
    them — so "smaller file" picked the worst-looking one available and the user got a
    visibly degraded video. Bitrate only decides when the resolution and codec already
    match, so the format-18 case below is untouched.
    """
    if bool(candidate.provider_format_id) != bool(incumbent.provider_format_id):
        return bool(candidate.provider_format_id)
    cand_codec = _CODEC_PREFERENCE.get(candidate.codec or "", 99)
    inc_codec = _CODEC_PREFERENCE.get(incumbent.codec or "", 99)
    if cand_codec != inc_codec:
        return cand_codec < inc_codec
    cand_br, inc_br = candidate.bitrate_kbps, incumbent.bitrate_kbps
    if cand_br and inc_br and cand_br != inc_br:
        return cand_br > inc_br
    cand_size, inc_size = candidate.approx_size_bytes, incumbent.approx_size_bytes
    if (cand_size is None) != (inc_size is None):
        return inc_size is None  # keep the option whose size we actually know
    return (cand_size or 0) < (inc_size or 0)


def _best_audio(audio_sources: list[MediaFormatOption]) -> MediaFormatOption | None:
    if not audio_sources:
        return None
    return max(audio_sources, key=lambda o: o.approx_size_bytes or 0)


def _audio_targets(
    audio_sources: list[MediaFormatOption], duration: int | None
) -> list[MediaFormatOption]:
    """One option per explicit codec target (D-041), each sized for how the worker
    actually produces it (per-codec default bitrate, or PCM for WAV / a fraction for
    FLAC). Falls back to the source size when duration is unknown so the catalog still
    appears. All targets point at the best source (the worker downloads ``bestaudio``)."""
    best = _best_audio(audio_sources)
    base_size = best.approx_size_bytes if best is not None else None
    provider_id = best.provider_format_id if best is not None else None
    # WAV/FLAC reflect the highest-fidelity source ("lossless" implies the best track);
    # YouTube's best audio is 48 kHz stereo. Take the max seen, defaulting when unknown.
    asr = max((o.asr for o in audio_sources if o.asr), default=0) or _DEFAULT_ASR
    channels = (
        max((o.channels for o in audio_sources if o.channels), default=0) or _DEFAULT_CHANNELS
    )
    out: list[MediaFormatOption] = []
    for target in AUDIO_TARGETS:
        size = _audio_target_size(target.quality, duration, base_size, asr, channels)
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


def _audio_target_size(
    quality: Quality, duration: int | None, base_size: int | None, asr: int, channels: int
) -> int | None:
    """Estimated bytes for one audio target — mirrors the transcoder's output."""
    if quality is Quality.WAV:
        pcm = _pcm_size(duration, asr, channels)
        return pcm if pcm is not None else _fallback_lossless(base_size)
    if quality is Quality.FLAC:
        pcm = _pcm_size(duration, asr, channels)
        if pcm is not None:
            return int(pcm * _FLAC_FRACTION_OF_PCM)
        return _fallback_lossless(base_size)
    kbps = _TARGET_KBPS.get(quality)
    if kbps is not None and duration:
        return int(kbps * 1000 / 8 * duration)
    return base_size  # duration unknown -> best-effort source size


def _pcm_size(duration: int | None, asr: int, channels: int) -> int | None:
    if not duration:
        return None
    return int(asr * channels * _PCM_BYTES_PER_SAMPLE * duration)


def _fallback_lossless(base_size: int | None) -> int | None:
    return base_size * _LOSSLESS_SIZE_MULTIPLIER if base_size else None
