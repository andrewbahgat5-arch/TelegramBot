"""Advertisement content types (MASTER_PLAN 10.10: ``advertisements.type``)."""

from __future__ import annotations

from enum import StrEnum


class AdType(StrEnum):
    """The media kind of an advertisement; default ``text``."""

    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
