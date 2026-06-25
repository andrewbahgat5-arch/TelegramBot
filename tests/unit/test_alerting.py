"""Unit tests for Telegram alerting (MASTER_PLAN Task 10.3, Section 15.6)."""

from __future__ import annotations

from core.alerting import (
    ALERT_WINDOW_SECONDS,
    AlertThrottle,
    TelegramAlertProcessor,
    alert_fingerprint,
    format_alert,
)


def test_throttle_allows_first_then_blocks_within_window() -> None:
    throttle = AlertThrottle(window_seconds=300)
    assert throttle.should_emit("fp", now=0.0) is True
    assert throttle.should_emit("fp", now=100.0) is False
    assert throttle.should_emit("fp", now=301.0) is True


def test_throttle_is_per_fingerprint() -> None:
    throttle = AlertThrottle()
    assert throttle.should_emit("a", now=0.0) is True
    assert throttle.should_emit("b", now=0.0) is True  # different fingerprint, not blocked


def test_default_window_is_five_minutes() -> None:
    assert ALERT_WINDOW_SECONDS == 300.0


def test_fingerprint_and_format() -> None:
    record = {"logger": "workers.main", "event": "db_unreachable", "job_id": "j1"}
    assert alert_fingerprint(record) == "workers.main:db_unreachable"
    text = format_alert(record)
    assert "CRITICAL" in text
    assert "db_unreachable" in text
    assert "job_id: j1" in text


def test_processor_emits_only_on_critical() -> None:
    sent: list[str] = []
    processor = TelegramAlertProcessor(sent.append)

    processor(None, "info", {"event": "noise"})
    processor(None, "warning", {"event": "still_noise"})
    assert sent == []

    processor(None, "critical", {"logger": "bot", "event": "boom"})
    assert len(sent) == 1
    assert "boom" in sent[0]


def test_processor_throttles_duplicate_criticals() -> None:
    sent: list[str] = []
    throttle = AlertThrottle(window_seconds=10_000)
    processor = TelegramAlertProcessor(sent.append, throttle=throttle)

    record = {"logger": "bot", "event": "boom"}
    processor(None, "critical", dict(record))
    processor(None, "critical", dict(record))
    assert len(sent) == 1  # second identical critical is throttled


def test_processor_returns_event_dict_unchanged() -> None:
    processor = TelegramAlertProcessor(lambda _text: None)
    event = {"event": "x", "logger": "y"}
    assert processor(None, "critical", event) is event
