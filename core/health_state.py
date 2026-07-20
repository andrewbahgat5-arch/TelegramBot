"""Dependency health as a state machine (DESIGN_MONITORING.md, Decision 1).

The Owner's "tell me immediately" list — database unavailable, Redis unavailable, queue
failure, storage failure, cookie pool exhausted — describes **system states, not
individual failures**. When Postgres drops, every in-flight request raises; alerting per
exception sends hundreds of messages for one outage, which is the flood the whole design
exists to avoid.

So health is tracked per dependency and only *transitions* are reportable:

    healthy ──▶ UNHEALTHY   one alert: what broke, how many checks failed
       ▲            │
       └─ RECOVERED ┘        one alert: recovered, and how long it was down

Individual exceptions during an outage go to the Logs table; the phone stays quiet
between the two transition alerts.

Pure — no I/O, no clock beyond an injected timestamp — so the alerting behaviour is
exhaustively testable without sleeping or standing up a database.

**Flap damping.** A dependency must fail ``threshold`` consecutive checks before it is
declared unhealthy. One dropped packet on a health probe is not an outage, and alerting
on it teaches the operator to ignore the channel. Recovery is reported on the *first*
success, because "it's working again" is never a false alarm worth suppressing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class HealthState(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class TransitionKind(StrEnum):
    WENT_DOWN = "went_down"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class Transition:
    """A reportable change. Anything that is not a transition is not worth an alert."""

    dependency: str
    kind: TransitionKind
    at: float
    detail: str = ""
    # Consecutive failed checks that led to WENT_DOWN.
    failure_count: int = 0
    # How long the outage lasted, set on RECOVERED.
    downtime_seconds: float | None = None

    @property
    def is_recovery(self) -> bool:
        return self.kind is TransitionKind.RECOVERED


@dataclass
class _Dependency:
    state: HealthState = HealthState.HEALTHY
    consecutive_failures: int = 0
    down_since: float | None = None
    last_detail: str = ""


@dataclass
class HealthMonitor:
    """Tracks several dependencies; returns a Transition only when one actually flips.

    ``threshold`` consecutive failures are required before declaring an outage. The
    default of 2 costs one extra probe interval of delay and removes single-blip noise.
    """

    threshold: int = 2
    _deps: dict[str, _Dependency] = field(default_factory=dict)

    def record(
        self, dependency: str, *, ok: bool, now: float, detail: str = ""
    ) -> Transition | None:
        dep = self._deps.setdefault(dependency, _Dependency())

        if ok:
            dep.consecutive_failures = 0
            if dep.state is HealthState.UNHEALTHY:
                downtime = now - dep.down_since if dep.down_since is not None else None
                dep.state = HealthState.HEALTHY
                dep.down_since = None
                dep.last_detail = ""
                return Transition(
                    dependency=dependency,
                    kind=TransitionKind.RECOVERED,
                    at=now,
                    downtime_seconds=downtime,
                )
            return None  # still healthy — nothing to say

        dep.consecutive_failures += 1
        dep.last_detail = detail or dep.last_detail
        if dep.state is HealthState.UNHEALTHY:
            return None  # already reported; stay quiet for the duration of the outage
        if dep.consecutive_failures < self.threshold:
            return None  # a blip, not an outage
        dep.state = HealthState.UNHEALTHY
        dep.down_since = now
        return Transition(
            dependency=dependency,
            kind=TransitionKind.WENT_DOWN,
            at=now,
            detail=dep.last_detail,
            failure_count=dep.consecutive_failures,
        )

    def state_of(self, dependency: str) -> HealthState:
        dep = self._deps.get(dependency)
        return dep.state if dep else HealthState.HEALTHY

    def unhealthy(self) -> tuple[str, ...]:
        return tuple(
            name for name, d in self._deps.items() if d.state is HealthState.UNHEALTHY
        )


def format_duration(seconds: float | None) -> str:
    """Human outage length — "4m12s" reads faster than "252.4" in an alert."""
    if seconds is None:
        return "unknown"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"
