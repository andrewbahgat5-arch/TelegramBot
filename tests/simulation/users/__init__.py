"""Simulated user profiles (MASTER_PLAN §25.15.1).

``PROFILE_REGISTRY`` maps the CLI ``--profile`` names to profile classes. The five
V1 profiles register here (Task 11.7); ``Premium`` is present but disabled until
the premium tier exists (V2).
"""

from __future__ import annotations

from tests.simulation.users.base import UserProfile

# Populated by the concrete profile modules (Task 11.7) via register_profile().
PROFILE_REGISTRY: dict[str, type[UserProfile]] = {}


def register_profile(cls: type[UserProfile]) -> type[UserProfile]:
    """Class decorator: register a profile under its ``name`` for CLI lookup."""
    PROFILE_REGISTRY[cls.name] = cls
    return cls


__all__ = ["PROFILE_REGISTRY", "UserProfile", "register_profile"]

# Import the concrete profiles so they self-register on package import. Placed at
# the bottom to avoid a circular import (they import register_profile from here).
# `Premium` is deliberately NOT imported here — it stays out of the registry until
# the V2 premium tier exists.
from tests.simulation.users import (  # noqa: E402, F401
    abuse,
    active,
    casual,
    heavy,
)
