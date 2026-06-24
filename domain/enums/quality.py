"""Selectable quality tiers (MASTER_PLAN 10.4: ``cached_files.quality``).

Persisted as VARCHAR(20). This enum is the canonical set of quality *labels* the
bot offers; yt-dlp's many concrete formats are normalized onto these labels during
format extraction (Sprint 5). Values are additive (MASTER_PLAN 9.4) — Sprint 5 may
add labels, but existing ones must never be removed or renamed.
"""

from __future__ import annotations

from enum import StrEnum


class Quality(StrEnum):
    # Video resolution ladder.
    P144 = "144p"
    P240 = "240p"
    P360 = "360p"
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"
    P2160 = "2160p"
    # Audio-only selection (paired with MediaFormat.AUDIO). ``AUDIO`` is the generic
    # "best native audio"; the per-codec members below are explicit targets the user
    # may pick (D-041). The codec is the persisted ``quality`` value, so the locked
    # ``(media_id, format, quality)`` cache key distinguishes codecs with no schema
    # change.
    AUDIO = "audio"
    MP3 = "mp3"
    M4A = "m4a"
    AAC = "aac"
    OGG = "ogg"
    OPUS = "opus"
    WAV = "wav"
    FLAC = "flac"
    # "Best available" — resolved by the provider when no specific tier is chosen.
    BEST = "best"

    @property
    def is_audio(self) -> bool:
        """Whether this tier denotes an audio selection (generic or per-codec)."""
        return self in _AUDIO_QUALITIES


_AUDIO_QUALITIES: frozenset[Quality] = frozenset(
    {
        Quality.AUDIO,
        Quality.MP3,
        Quality.M4A,
        Quality.AAC,
        Quality.OGG,
        Quality.OPUS,
        Quality.WAV,
        Quality.FLAC,
    }
)
