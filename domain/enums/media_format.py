"""High-level media format kinds (MASTER_PLAN 2.3 scope: video + audio).

The ``cached_files.format`` / ``jobs.format`` columns are VARCHAR(50); this enum
captures the user-selectable *kind*. Provider-specific format codes from yt-dlp
are mapped onto these kinds during format extraction (Sprint 5). Values are
additive (MASTER_PLAN 9.4); never remove one.
"""

from __future__ import annotations

from enum import StrEnum


class MediaFormat(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
