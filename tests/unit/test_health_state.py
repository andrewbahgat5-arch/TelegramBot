"""Dependency health state machine — the anti-flood contract (DESIGN_MONITORING.md)."""

from __future__ import annotations

from core.health_state import (
    HealthMonitor,
    HealthState,
    TransitionKind,
    format_duration,
)


def test_a_single_failed_check_is_not_an_outage() -> None:
    """One dropped packet on a probe must not page anyone."""
    m = HealthMonitor(threshold=2)
    assert m.record("database", ok=False, now=0) is None
    assert m.state_of("database") is HealthState.HEALTHY


def test_going_down_reports_exactly_once() -> None:
    """THE point of the design: one outage is one alert, not one per failing request."""
    m = HealthMonitor(threshold=2)
    m.record("database", ok=False, now=0)
    t = m.record("database", ok=False, now=10, detail="connection refused")
    assert t is not None and t.kind is TransitionKind.WENT_DOWN
    assert t.failure_count == 2
    assert "connection refused" in t.detail

    # 500 more failures during the same outage say nothing further.
    for i in range(500):
        assert m.record("database", ok=False, now=20 + i) is None


def test_recovery_reports_once_with_the_outage_duration() -> None:
    m = HealthMonitor(threshold=2)
    m.record("redis", ok=False, now=0)
    m.record("redis", ok=False, now=5)  # down at t=5
    t = m.record("redis", ok=True, now=257)
    assert t is not None and t.is_recovery
    assert t.downtime_seconds == 252
    assert m.state_of("redis") is HealthState.HEALTHY
    # Staying healthy is not news.
    assert m.record("redis", ok=True, now=300) is None


def test_recovery_is_reported_on_the_first_success() -> None:
    """"It's working again" is never a false alarm worth damping."""
    m = HealthMonitor(threshold=3)
    for i in range(3):
        m.record("queue", ok=False, now=i)
    assert m.record("queue", ok=True, now=10) is not None


def test_a_blip_resets_the_failure_run() -> None:
    """Fail, recover, fail must not accumulate into a false outage."""
    m = HealthMonitor(threshold=3)
    m.record("storage", ok=False, now=0)
    m.record("storage", ok=False, now=1)
    assert m.record("storage", ok=True, now=2) is None  # was never declared down
    m.record("storage", ok=False, now=3)
    assert m.record("storage", ok=False, now=4) is None  # only 2 in the new run
    assert m.state_of("storage") is HealthState.HEALTHY


def test_dependencies_are_tracked_independently() -> None:
    m = HealthMonitor(threshold=1)
    m.record("database", ok=False, now=0)
    assert m.state_of("database") is HealthState.UNHEALTHY
    assert m.state_of("redis") is HealthState.HEALTHY
    assert m.unhealthy() == ("database",)


def test_full_outage_cycle_produces_exactly_two_alerts() -> None:
    """The end-to-end guarantee: an outage spanning 1000 checks = 2 messages."""
    m = HealthMonitor(threshold=2)
    alerts = []
    for i in range(1000):
        t = m.record("database", ok=False, now=i)
        if t:
            alerts.append(t)
    for i in range(10):
        t = m.record("database", ok=True, now=1000 + i)
        if t:
            alerts.append(t)
    assert len(alerts) == 2
    assert alerts[0].kind is TransitionKind.WENT_DOWN
    assert alerts[1].kind is TransitionKind.RECOVERED


def test_format_duration_is_readable() -> None:
    assert format_duration(45) == "45s"
    assert format_duration(252) == "4m12s"
    assert format_duration(3900) == "1h05m"
    assert format_duration(None) == "unknown"
