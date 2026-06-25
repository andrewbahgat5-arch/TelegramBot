"""Readiness evaluation (MASTER_PLAN Task 10.4, Section 15.7).

``/v1/ready`` is green only when the database and Redis answer a ping within
500 ms, the queue depth is readable, and at least one worker heartbeat is present
(Section 15.7). This module is pure — it depends only on ``core``/stdlib and runs
injected async probe callables, so the infrastructure concretes stay confined to
``api/main.py`` (the composition root, per the Section 8.2 dependency rule).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

# A ping probe completes (returns) when healthy and raises on failure.
PingProbe = Callable[[], Awaitable[None]]
# A count probe returns a non-negative integer (queue depth, active workers).
CountProbe = Callable[[], Awaitable[int]]

_DEFAULT_TIMEOUT_SECONDS = 0.5  # Section 15.7: DB/Redis ping ≤ 500 ms.


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    detail: str


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, CheckResult]


class ReadinessChecker:
    """Run the Section 15.7 readiness checks against injected probes."""

    def __init__(
        self,
        *,
        db_ping: PingProbe,
        redis_ping: PingProbe,
        queue_depth: CountProbe,
        active_workers: CountProbe,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._db_ping = db_ping
        self._redis_ping = redis_ping
        self._queue_depth = queue_depth
        self._active_workers = active_workers
        self._timeout = timeout_seconds

    async def check(self) -> ReadinessReport:
        db, redis, queue, workers = await asyncio.gather(
            self._ping("database", self._db_ping),
            self._ping("redis", self._redis_ping),
            self._count("queue", self._queue_depth, minimum=0),
            self._count("workers", self._active_workers, minimum=1),
        )
        checks = {"database": db, "redis": redis, "queue": queue, "workers": workers}
        ready = all(result.ok for result in checks.values())
        return ReadinessReport(ready=ready, checks=checks)

    async def _ping(self, name: str, probe: PingProbe) -> CheckResult:
        try:
            await asyncio.wait_for(probe(), timeout=self._timeout)
        except TimeoutError:
            return CheckResult(False, f"{name} ping exceeded {self._timeout * 1000:.0f} ms")
        except Exception as exc:  # boundary: a probe failure is a readiness signal, not a crash
            return CheckResult(False, f"{name} ping failed: {exc}")
        return CheckResult(True, "ok")

    async def _count(self, name: str, probe: CountProbe, *, minimum: int) -> CheckResult:
        try:
            value = await asyncio.wait_for(probe(), timeout=self._timeout)
        except TimeoutError:
            return CheckResult(False, f"{name} read exceeded {self._timeout * 1000:.0f} ms")
        except Exception as exc:  # boundary: a probe failure is a readiness signal, not a crash
            return CheckResult(False, f"{name} read failed: {exc}")
        if value < minimum:
            return CheckResult(False, f"{name}={value} (need ≥ {minimum})")
        return CheckResult(True, f"{name}={value}")
