"""Advertisement placement + delivery mode (MASTER_PLAN Sprint 9.5, D-042/D-044).

``AdPlacement`` is where a persistent ad appears in the bot flow; ``post_download`` is
the Sprint 9 compatibility placement (shown after any delivery). ``AdDeliveryMode``
selects how an ad is rendered: ``fields`` (programmatic) or ``copy`` (re-send a stored
Telegram message via ``copyMessage``).
"""

from __future__ import annotations

from enum import StrEnum


class AdPlacement(StrEnum):
    """Where an ad is shown (``advertisements.placement``)."""

    POST_DOWNLOAD = "post_download"  # Sprint 9 compat: after any delivery
    VIDEO_DELIVERY = "video_delivery"
    AUDIO_DELIVERY = "audio_delivery"
    QUALITY_SELECT = "quality_select"
    HOME = "home"
    HISTORY = "history"
    BROADCAST = "broadcast"  # never auto-shown; delivered only via /ad_broadcast


class AdDeliveryMode(StrEnum):
    """How an ad is rendered (``advertisements.delivery_mode``)."""

    FIELDS = "fields"  # programmatic: type + text + file_id + buttons
    COPY = "copy"  # copyMessage of a stored source message (rich content)
    RICH = "rich"  # sendRichMessage of Rich Markdown (headings/lists/details/…) source
