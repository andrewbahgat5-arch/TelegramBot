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
    # Audio-only selection (paired with MediaFormat.AUDIO).
    AUDIO = "audio"
    # "Best available" — resolved by the provider when no specific tier is chosen.
    BEST = "best"
