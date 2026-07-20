"""Dependency watchdog: poll readiness, alert only on transitions.

Wraps the existing :class:`ReadinessChecker` (which already probes database, redis,
queue and workers) in the :class:`HealthMonitor` state machine, so an outage produces
exactly two Telegram messages — one when it starts, one when it ends — regardless of
how long it lasts or how many requests fail meanwhile.

This is the *only* place allowed to raise a CRITICAL for infrastructure. Individual
exceptions caused by the same outage are Logs rows; see DESIGN_MONITORING.md.

Not covered here, deliberately: **the process being dead**. A crashed app cannot send
its own alert, so liveness is uptime-kuma's job — it probes ``/v1/ready`` from outside
and alerts when nothing answers. This watchdog reports the app's dependencies; kuma
reports the app.
"""

from __future__ import annotations

import asyncio
import time

from core.error_report import ErrorReport, RequestContext, Severity
from core.health_state import HealthMonitor, Transition, format_duration
from core.logging import get_logger
from services.error_report_service import ErrorReportService

_log = get_logger("services.health_watchdog")

# Slow enough not to add meaningful load, fast enough that a real outage is known
# within about a minute (threshold=2 means two consecutive misses).
DEFAULT_INTERVAL_SECONDS = 30.0


class HealthWatchdog:
    def __init__(
        self,
        checker: object,  # ReadinessChecker — structural, keeps this import-light
        reporter: ErrorReportService,
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        monitor: HealthMonitor | None = None,
    ) -> None:
        self._checker = checker
        self._reporter = reporter
        self._interval = interval_seconds
        self._monitor = monitor or HealthMonitor()

    async def poll_once(self, *, now: float | None = None) -> list[Transition]:
        """One sweep. Returns the transitions found (empty on a boring, healthy cycle)."""
        ts = now if now is not None else time.time()
        try:
            report = await self._checker.check()  # type: ignore[attr-defined]
        except Exception as exc:
            # The checker itself failing IS a signal — treat it as everything unknown
            # rather than silently skipping the cycle.
            _log.warning("health_check_failed", error=str(exc))
            transition = self._monitor.record(
                "readiness", ok=False, now=ts, detail=f"health check raised: {exc}"
            )
            return [transition] if transition else []

        transitions: list[Transition] = []
        for name, result in report.checks.items():
            transition = self._monitor.record(
                name, ok=result.ok, now=ts, detail=result.detail
            )
            if transition is not None:
                transitions.append(transition)
        return transitions

    async def report(self, transitions: list[Transition]) -> None:
        """Send ONE message per poll, however many dependencies flipped in it.

        A real staging outage showed why: stopping redis produced three separate
        CRITICALs — redis, queue and workers — because the queue and worker probes both
        read redis, so one root cause fanned out into three alarms. They share a cause,
        a timestamp and a fix, so they belong in one message; three is the same
        alert-storm problem this design exists to prevent, one level down.
        """
        if not transitions:
            return
        if len(transitions) == 1:
            await self._reporter.deliver(_to_report(transitions[0]))
            return
        await self._reporter.deliver(_combined_report(transitions))

    async def run(self) -> None:
        """Poll forever. Never exits on error — a watchdog that dies is worse than none."""
        _log.info("health_watchdog_started", interval_seconds=self._interval)
        while True:
            try:
                await self.report(await self.poll_once())
            except Exception as exc:
                _log.warning("health_watchdog_cycle_failed", error=str(exc))
            await asyncio.sleep(self._interval)


def _to_report(transition: Transition) -> ErrorReport:
    """Render a transition as the report the Owner receives.

    Recovery is CRITICAL too — not because it is bad news, but because it closes an
    alert the operator is already holding. An unresolved 🔴 with no 🟢 is worse than
    either message alone.
    """
    if transition.is_recovery:
        return ErrorReport(
            severity=Severity.CRITICAL,
            kind=f"{transition.dependency}_recovered",
            message=(
                f"✅ {transition.dependency} recovered after "
                f"{format_duration(transition.downtime_seconds)}"
            ),
            request=RequestContext(stage="health_check"),
        )
    return ErrorReport(
        severity=Severity.CRITICAL,
        kind=f"{transition.dependency}_unavailable",
        message=(
            f"{transition.dependency} is unavailable after "
            f"{transition.failure_count} consecutive checks — {transition.detail}"
        ),
        request=RequestContext(stage="health_check"),
    )


def _combined_report(transitions: list[Transition]) -> ErrorReport:
    """Several dependencies flipped in the same sweep — almost always one root cause."""
    down = [t for t in transitions if not t.is_recovery]
    up = [t for t in transitions if t.is_recovery]
    names = ", ".join(t.dependency for t in (down or up))
    lines: list[str] = []
    if down:
        lines.append(
            f"{len(down)} dependencies unavailable: {', '.join(t.dependency for t in down)}"
        )
        # The detail is the same string for every dependent probe, so show it once.
        lines.append(down[0].detail)
    if up:
        lines.append(
            "recovered: "
            + ", ".join(
                f"{t.dependency} after {format_duration(t.downtime_seconds)}" for t in up
            )
        )
    kind = f"{len(down)}_dependencies_unavailable" if down else "dependencies_recovered"
    return ErrorReport(
        severity=Severity.CRITICAL,
        kind=kind,
        message=" — ".join(line for line in lines if line),
        request=RequestContext(stage="health_check", worker_id=names),
    )
