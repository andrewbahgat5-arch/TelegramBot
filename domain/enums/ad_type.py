"""Advertisement content types (MASTER_PLAN 10.10: ``advertisements.type``)."""

from __future__ import annotations

from enum import StrEnum


class AdType(StrEnum):
    """The media kind of an advertisement; default ``text``.

    ``document``/``audio``/``album`` were added in Sprint 9.5 (Ads v2); ``album`` is a
    media group delivered via the copy-mode path.
    """

    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"
    DOCUMENT = "document"
    AUDIO = "audio"
    ALBUM = "album"
