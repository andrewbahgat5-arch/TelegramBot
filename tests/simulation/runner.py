"""SimulationRunner + CLI (MASTER_PLAN §25.15.8, §25.15.9).

Orchestrates a load level: instantiates profiles, drives their action streams
through a :class:`BotClient`, and collects metrics. Reproducible with a fixed
``--seed``. Production credentials are rejected in ``SimulationRunner.__init__``
(§25.15.10).

Invocation (the LOCKED §25.15.9 form):

    python -m tests.simulation.runner --level=L1 --profile=Casual --seed=42

The default transport is the deterministic in-memory stub (no live bot). The live
sandbox transport is Phase B (requires the Task 11.1 sandbox provisioning).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from pathlib import Path

from pydantic import ValidationError

from core.config import Settings
from core.environment import evaluate_environment_safety
from tests.simulation.bot_client.client import BotClient, StubBotClient
from tests.simulation.metrics.collector import MetricsCollector, RunSummary
from tests.simulation.users import PROFILE_REGISTRY
from tests.simulation.users.base import UserProfile

REPO_ROOT = Path(__file__).resolve().parents[2]

# LOCKED load levels (D-035, §25.10.1): level → simulated user count.
LOAD_LEVELS: dict[str, int] = {
    "L1": 10,
    "L2": 50,
    "L3": 100,
    "L4": 500,
    "L5": 1000,
    "L6": 5000,
}


class ProductionCredentialsError(RuntimeError):
    """Raised when the simulator is pointed at a production deployment."""


def reject_production_credentials(settings: Settings) -> None:
    """Refuse to run against production (§25.15.10).

    Blocks a ``production`` deployment outright and reuses the D-060 environment
    safety rules (e.g. a test deployment carrying the production bot token).
    """
    if settings.is_production:
        raise ProductionCredentialsError(
            "refusing to run the simulator against a production deployment (DEPLOY_ENV=production)"
        )
    violations = evaluate_environment_safety(settings)
    if violations:
        raise ProductionCredentialsError("; ".join(violations))


class SimulationRunner:
    """Drives a load level deterministically and returns a :class:`RunSummary`."""

    def __init__(
        self,
        *,
        settings: Settings,
        client: BotClient,
        seed: int | None = None,
    ) -> None:
        reject_production_credentials(settings)
        self._settings = settings
        self._client = client
        self._seed = seed

    async def run(
        self,
        *,
        level: str,
        profiles: list[type[UserProfile]],
        honor_delays: bool = False,
    ) -> RunSummary:
        if level not in LOAD_LEVELS:
            raise ValueError(f"unknown load level {level!r}; expected one of {sorted(LOAD_LEVELS)}")
        if not profiles:
            raise ValueError("at least one profile is required")
        count = LOAD_LEVELS[level]
        collector = MetricsCollector()
        start = time.perf_counter()
        base_seed = self._seed or 0
        for i in range(count):
            profile_cls = profiles[i % len(profiles)]
            user_rng = random.Random(base_seed * 1_000_003 + i)  # noqa: S311 - not crypto
            profile = profile_cls(user_id=i + 1, rng=user_rng)
            for action in profile.actions():
                if honor_delays and action.delay_before:
                    await asyncio.sleep(action.delay_before)
                collector.record(await self._client.perform(profile.user_id, action))
        wall = time.perf_counter() - start
        return collector.summarize(wall)


def _resolve_settings(env_file: str | None) -> Settings:
    if env_file:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError:
        # Dev/CI without a populated .env → fall back to the example template.
        return Settings(_env_file=str(REPO_ROOT / ".env.example"))  # type: ignore[call-arg]


def _resolve_profiles(names: str) -> list[type[UserProfile]]:
    selected: list[type[UserProfile]] = []
    for raw in names.split(","):
        name = raw.strip()
        if not name:
            continue
        if name not in PROFILE_REGISTRY:
            raise SystemExit(
                f"unknown profile {name!r}; available: {sorted(PROFILE_REGISTRY) or '(none yet)'}"
            )
        selected.append(PROFILE_REGISTRY[name])
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Telegram bot load/simulation runner")
    parser.add_argument("--level", default="L1", choices=sorted(LOAD_LEVELS))
    parser.add_argument("--profile", default="Casual", help="comma-separated profile names")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--duration", type=int, default=None, help="reserved for live runs")
    parser.add_argument("--env-file", default=None)
    args = parser.parse_args(argv)

    settings = _resolve_settings(args.env_file)
    profiles = _resolve_profiles(args.profile)
    client = StubBotClient(rng=random.Random(args.seed))  # noqa: S311 - not crypto
    runner = SimulationRunner(settings=settings, client=client, seed=args.seed)
    summary = asyncio.run(runner.run(level=args.level, profiles=profiles))
    print(json.dumps({"level": args.level, "profiles": args.profile, **summary.as_dict()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
