"""Telegram alerting (MASTER_PLAN Task 10.3, Section 15.6).

A structlog processor that forwards ``CRITICAL`` log records to an injected sink
(the composition root wires the sink to a Telegram send). Alerts are throttled to
one message per fingerprint per window (Section 15.6: one per 5 minutes) so a
flapping failure cannot spam the alert channel. This module is pure — it depends
only on stdlib; the Telegram concrete lives in ``infrastructure`` and is injected.
"""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from typing import Any

EventDict = MutableMapping[str, Any]

# Section 15.6: throttle to one message per fingerprint per 5 minutes.
ALERT_WINDOW_SECONDS = 300.0

AlertSink = Callable[[str], None]


class AlertThrottle:
    """Deduplicate alerts: at most one per fingerprint per ``window_seconds``."""

    def __init__(self, window_seconds: float = ALERT_WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._last_sent: dict[str, float] = {}

    def should_emit(self, fingerprint: str, *, now: float | None = None) -> bool:
        ts = now if now is not None else time.time()
        last = self._last_sent.get(fingerprint)
        if last is not None and ts - last < self._window:
            return False
        self._last_sent[fingerprint] = ts
        return True


def alert_fingerprint(event_dict: EventDict) -> str:
    """Stable fingerprint for an alert: the originating logger + event name."""
    return f"{event_dict.get('logger', '?')}:{event_dict.get('event', '?')}"


def format_alert(event_dict: EventDict) -> str:
    """Render a concise, single-message alert from a log record."""
    event = event_dict.get("event", "critical")
    logger = event_dict.get("logger", "?")
    lines = [f"🚨 CRITICAL: {event}", f"component: {event_dict.get('component', logger)}"]
    for key in ("correlation_id", "job_id", "worker_id", "error"):
        value = event_dict.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


class TelegramAlertProcessor:
    """structlog processor forwarding ``CRITICAL`` records to the alert sink."""

    def __init__(self, sink: AlertSink, *, throttle: AlertThrottle | None = None) -> None:
        self._sink = sink
        self._throttle = throttle or AlertThrottle()

    def __call__(self, _logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
        if method_name == "critical" and self._throttle.should_emit(alert_fingerprint(event_dict)):
            self._sink(format_alert(event_dict))
        return event_dict
