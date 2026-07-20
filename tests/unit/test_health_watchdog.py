"""Watchdog: readiness → transitions → exactly two alerts per outage."""

from __future__ import annotations

from dataclasses import dataclass

from core.error_report import Severity
from services.error_report_service import ErrorReportService
from services.health_watchdog import HealthWatchdog


@dataclass
class _Result:
    ok: bool
    detail: str = "ok"


@dataclass
class _Report:
    checks: dict[str, _Result]


class _Checker:
    def __init__(self) -> None:
        self.db_ok = True
        self.raises = False

    async def check(self) -> _Report:
        if self.raises:
            raise RuntimeError("checker exploded")
        return _Report(
            checks={
                "database": _Result(self.db_ok, "connection refused" if not self.db_ok else "ok"),
                "redis": _Result(True),
            }
        )


class _Sink:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def __call__(self, text: str) -> None:
        self.sent.append(text)


def _watchdog() -> tuple[HealthWatchdog, _Checker, _Sink]:
    checker, sink = _Checker(), _Sink()
    return HealthWatchdog(checker, ErrorReportService(sink)), checker, sink


async def test_healthy_polling_is_silent() -> None:
    wd, _checker, sink = _watchdog()
    for i in range(20):
        await wd.report(await wd.poll_once(now=i))
    assert sink.sent == []


async def test_one_outage_produces_exactly_two_messages() -> None:
    """The whole point: an outage spanning 100 polls is 🔴 once and 🟢 once."""
    wd, checker, sink = _watchdog()
    await wd.report(await wd.poll_once(now=0))

    checker.db_ok = False
    for i in range(1, 100):
        await wd.report(await wd.poll_once(now=i))
    assert len(sink.sent) == 1
    assert "🔴" in sink.sent[0]
    assert "database_unavailable" in sink.sent[0]
    assert "connection refused" in sink.sent[0]

    checker.db_ok = True
    for i in range(100, 120):
        await wd.report(await wd.poll_once(now=i))
    assert len(sink.sent) == 2
    assert "database_recovered" in sink.sent[1]


async def test_recovery_message_states_the_outage_duration() -> None:
    wd, checker, sink = _watchdog()
    await wd.poll_once(now=0)
    checker.db_ok = False
    await wd.poll_once(now=10)
    await wd.report(await wd.poll_once(now=20))  # declared down at t=20
    checker.db_ok = True
    await wd.report(await wd.poll_once(now=272))
    assert "4m12s" in sink.sent[-1]


async def test_infra_alerts_reach_telegram_despite_critical_only_routing() -> None:
    """These are exactly the events the Owner wants pushed, so they must be CRITICAL —
    the default routing drops anything lower."""
    wd, checker, sink = _watchdog()
    checker.db_ok = False
    await wd.report(await wd.poll_once(now=0))
    await wd.report(await wd.poll_once(now=1))
    assert len(sink.sent) == 1  # arrived under the CRITICAL-only default
    assert Severity.CRITICAL.emoji in sink.sent[0]


async def test_a_broken_checker_is_itself_reported() -> None:
    """A health check that raises must not silently skip the cycle."""
    wd, checker, sink = _watchdog()
    checker.raises = True
    await wd.report(await wd.poll_once(now=0))
    await wd.report(await wd.poll_once(now=1))
    assert len(sink.sent) == 1
    assert "readiness_unavailable" in sink.sent[0]


async def test_one_root_cause_produces_one_message_not_three() -> None:
    """REGRESSION from a real staging outage: stopping redis flipped redis, queue AND
    workers in the same sweep (both dependents probe redis), producing three separate
    CRITICALs for one root cause. They share a cause and a fix — one message."""

    class _Multi:
        def __init__(self) -> None:
            self.ok = True

        async def check(self) -> _Report:
            d = _Result(self.ok, "connection refused" if not self.ok else "ok")
            return _Report(checks={"redis": d, "queue": d, "workers": d})

    checker, sink = _Multi(), _Sink()
    wd = HealthWatchdog(checker, ErrorReportService(sink))
    await wd.report(await wd.poll_once(now=0))
    checker.ok = False
    for i in range(1, 40):
        await wd.report(await wd.poll_once(now=i))
    assert len(sink.sent) == 1
    assert "3 dependencies unavailable" in sink.sent[0]
    for name in ("redis", "queue", "workers"):
        assert name in sink.sent[0]

    checker.ok = True
    for i in range(40, 50):
        await wd.report(await wd.poll_once(now=i))
    assert len(sink.sent) == 2  # one combined recovery, not three
    assert "recovered" in sink.sent[1]
