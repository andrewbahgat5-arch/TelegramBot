"""Stress-scenario catalog ST-1 .. ST-6 (MASTER_PLAN §25.15.6, component §25.15.8).

Each :class:`StressScenario` records the scenario, its LOCKED expected behavior,
and (for the load-shaped ones) a deterministic traffic-plan builder. The
fault-injection scenarios (provider outage, DB slowdown, Redis restart) carry no
plan builder: they require the live test infra and are executed in Phase B
(Task 11.11). The catalog itself — ids, expectations, and the load plans — is the
Phase-A deliverable.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from tests.simulation.traffic.base import TrafficPlan
from tests.simulation.traffic.generators import RandomTraffic, ScheduledSpike

PlanBuilder = Callable[[random.Random], TrafficPlan]


@dataclass(frozen=True, slots=True)
class StressScenario:
    id: str
    name: str
    expected_behavior: str
    kind: str  # "load" (traffic-shaped) or "fault" (fault-injection)
    plan_builder: PlanBuilder | None = None

    @property
    def requires_live_infra(self) -> bool:
        """All stress assertions need the real system; only plan *shape* runs dry."""
        return True


def _st1_plan(rng: random.Random) -> TrafficPlan:
    # 100 -> 1000 users in 30 s: a heavy spike at the tail of a 60 s window.
    return ScheduledSpike(spike_fraction=0.9, spike_window_s=30.0).plan(
        total_users=1000, rng=rng, window_s=60.0
    )


def _st2_plan(rng: random.Random) -> TrafficPlan:
    # Queue flood: 5000 aggressive arrivals within 60 s.
    flood_mix = {"Heavy": 0.6, "Active": 0.3, "Abuse": 0.1}
    return RandomTraffic(mix=flood_mix).plan(total_users=5000, rng=rng, window_s=60.0)


STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario(
        id="ST-1",
        name="100 -> 1000 users in 30 s",
        expected_behavior="Queue absorbs; SLO p95 may degrade; no errors; no data loss.",
        kind="load",
        plan_builder=_st1_plan,
    ),
    StressScenario(
        id="ST-2",
        name="Queue flood (5000 jobs in 60 s)",
        expected_behavior="Backpressure surfaces; jobs eventually drain; no data loss.",
        kind="load",
        plan_builder=_st2_plan,
    ),
    StressScenario(
        id="ST-3",
        name="Cache invalidation storm",
        expected_behavior=(
            "Cache rebuilds without thundering-herd; rate-limit applies to redownload bursts."
        ),
        kind="fault",
    ),
    StressScenario(
        id="ST-4",
        name="Provider outage (kill primary, no secondary)",
        expected_behavior="Clear user-facing error; registry retries after cooldown.",
        kind="fault",
    ),
    StressScenario(
        id="ST-5",
        name="Database slowdown (artificial 1 s latency)",
        expected_behavior="Timeouts surface gracefully; bot reports degraded mode.",
        kind="fault",
    ),
    StressScenario(
        id="ST-6",
        name="Redis restart",
        expected_behavior=(
            "Active downloads resume from active_downloads PG; no duplicate work; "
            "no lost user data."
        ),
        kind="fault",
    ),
)


class ScenarioCatalog:
    """Registry of the LOCKED stress scenarios."""

    _BY_ID: ClassVar[dict[str, StressScenario]] = {s.id: s for s in STRESS_SCENARIOS}

    @classmethod
    def all(cls) -> tuple[StressScenario, ...]:
        return STRESS_SCENARIOS

    @classmethod
    def ids(cls) -> list[str]:
        return [s.id for s in STRESS_SCENARIOS]

    @classmethod
    def get(cls, scenario_id: str) -> StressScenario:
        if scenario_id not in cls._BY_ID:
            raise KeyError(f"unknown stress scenario {scenario_id!r}; expected {cls.ids()}")
        return cls._BY_ID[scenario_id]


__all__ = ["STRESS_SCENARIOS", "ScenarioCatalog", "StressScenario"]
