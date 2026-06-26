"""Ad analytics event type (MASTER_PLAN Sprint 9.5.9, D-045).

``AdEventType`` labels a row in the ``ad_events`` per-event analytics table. The
per-ad / per-button counters on ``advertisements`` / ``ad_buttons`` remain the hot
path and the source of truth; ``ad_events`` is the additive, time-series route for
per-placement reporting, written off the delivery hot path (D-052).
"""

from __future__ import annotations

from enum import StrEnum


class AdEventType(StrEnum):
    """The kind of recorded ad event (``ad_events.event_type``)."""

    IMPRESSION = "impression"
    CLICK = "click"
