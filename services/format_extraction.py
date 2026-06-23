"""Provider-agnostic format post-processing (MASTER_PLAN Task 5.6).

A provider's ``extract_info`` may return many raw format options (one per concrete
vendor format). ``normalize_formats`` collapses them to one option per
``(format, quality)`` and sorts them for display: video first (best quality first),
then audio. Pure and provider-independent — it must never reference a vendor.
"""

from __future__ import annotations

from collections.abc import Iterable

from domain.entities.media import MediaFormatOption
from domain.enums import MediaFormat, Quality

# Display rank for a quality tier (higher sorts first within a format group).
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
    Quality.AUDIO: 0,
}


def normalize_formats(options: Iterable[MediaFormatOption]) -> tuple[MediaFormatOption, ...]:
    """Deduplicate by ``(format, quality)`` and sort for the selection keyboard."""
    best: dict[tuple[MediaFormat, Quality], MediaFormatOption] = {}
    for option in options:
        key = (option.format, option.quality)
        incumbent = best.get(key)
        if incumbent is None or _prefer(option, incumbent):
            best[key] = option
    return tuple(sorted(best.values(), key=_sort_key))


def _prefer(candidate: MediaFormatOption, incumbent: MediaFormatOption) -> bool:
    """Prefer a concrete (provider-resolvable) option, then the larger/richer one."""
    if bool(candidate.provider_format_id) != bool(incumbent.provider_format_id):
        return bool(candidate.provider_format_id)
    return (candidate.approx_size_bytes or 0) > (incumbent.approx_size_bytes or 0)


def _sort_key(option: MediaFormatOption) -> tuple[int, int]:
    # Video group (0) before audio group (1); within a group, higher quality first.
    group = 0 if option.format is MediaFormat.VIDEO else 1
    return (group, -_QUALITY_RANK.get(option.quality, 0))
