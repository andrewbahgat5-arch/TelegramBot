"""AI-controlled traffic generation (MASTER_PLAN §25.15.3).

``TRAFFIC_REGISTRY`` maps generator names to classes for CLI / programmatic
selection. The five V1 generators self-register on import.
"""

from __future__ import annotations

from tests.simulation.traffic.base import Spawn, TrafficGenerator, TrafficPlan

TRAFFIC_REGISTRY: dict[str, type[TrafficGenerator]] = {}


def register_generator(cls: type[TrafficGenerator]) -> type[TrafficGenerator]:
    """Class decorator: register a traffic generator under its ``name``."""
    TRAFFIC_REGISTRY[cls.name] = cls
    return cls


__all__ = [
    "TRAFFIC_REGISTRY",
    "Spawn",
    "TrafficGenerator",
    "TrafficPlan",
    "register_generator",
]

# Import the concrete generators so they self-register (bottom to avoid a cycle).
from tests.simulation.traffic import generators  # noqa: E402, F401
