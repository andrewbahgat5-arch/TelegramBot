"""Unit tests for the simulation framework skeleton (MASTER_PLAN Task 11.6).

The framework lives under ``tests/simulation/`` (not a pytest collection root), so
its self-tests live here to stay in the gated suite.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.config import Settings
from core.security import token_fingerprint
from tests.simulation.actions import ActionKind, ActionResult, SimulatedAction
from tests.simulation.bot_client.client import StubBotClient
from tests.simulation.metrics.collector import MetricsCollector
from tests.simulation.metrics.report_writer import ReportWriter
from tests.simulation.runner import (
    LOAD_LEVELS,
    ProductionCredentialsError,
    SimulationRunner,
    reject_production_credentials,
)
from tests.simulation.users.base import UserProfile

ENV_EXAMPLE = str(Path(__file__).resolve().parents[2] / ".env.example")


def _settings() -> Settings:
    return Settings(_env_file=ENV_EXAMPLE)  # type: ignore[call-arg]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - deterministic test data, not crypto


def _stub(seed: int) -> StubBotClient:
    return StubBotClient(rng=_rng(seed))


class _NormalProfile(UserProfile):
    name = "normal-test"

    def actions(self) -> Iterator[SimulatedAction]:
        yield SimulatedAction(ActionKind.START, delay_before=5.0)
        yield SimulatedAction(ActionKind.SEND_URL, delay_before=5.0, url=self._pick_url())
        yield SimulatedAction(ActionKind.CLICK_QUALITY, delay_before=5.0, is_download=True)


class _RapidProfile(UserProfile):
    name = "rapid-test"

    def actions(self) -> Iterator[SimulatedAction]:
        for _ in range(5):  # rapid-fire downloads, zero think-time
            yield SimulatedAction(ActionKind.CLICK_QUALITY, delay_before=0.0, is_download=True)


# --- production-credential rejection (§25.15.10) --------------------------
def test_runner_rejects_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_ENV", "production")
    settings = _settings()
    with pytest.raises(ProductionCredentialsError):
        SimulationRunner(settings=settings, client=_stub(1), seed=1)


def test_reject_helper_allows_development() -> None:
    reject_production_credentials(_settings())  # development default → no raise


def test_test_env_with_prod_fingerprint_cannot_even_build_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Defense in depth: the Settings model-validator (D-060) blocks this before the
    # runner is reached.
    monkeypatch.setenv("DEPLOY_ENV", "test")
    monkeypatch.setenv("PROD_BOT_TOKEN_FINGERPRINT", token_fingerprint("bot-token-test-XXXX"))
    from core.environment import EnvironmentMisconfiguredError

    with pytest.raises(EnvironmentMisconfiguredError):
        _settings()


# --- runner determinism + correctness -------------------------------------
async def test_run_is_deterministic_with_seed() -> None:
    async def _run() -> dict[str, float | int]:
        runner = SimulationRunner(settings=_settings(), client=_stub(42), seed=42)
        summary = (await runner.run(level="L1", profiles=[_NormalProfile])).as_dict()
        # throughput is wall-clock dependent; everything else is seed-deterministic.
        summary.pop("throughput_per_s")
        return summary

    assert await _run() == await _run()


async def test_normal_profile_downloads_succeed() -> None:
    runner = SimulationRunner(settings=_settings(), client=_stub(7), seed=7)
    summary = await runner.run(level="L1", profiles=[_NormalProfile])
    assert summary.total == LOAD_LEVELS["L1"] * 3
    assert summary.successful_downloads == LOAD_LEVELS["L1"]
    assert summary.blocked_downloads == 0


async def test_rapid_fire_downloads_all_blocked() -> None:
    runner = SimulationRunner(settings=_settings(), client=_stub(3), seed=3)
    summary = await runner.run(level="L1", profiles=[_RapidProfile])
    assert summary.successful_downloads == 0
    assert summary.blocked_downloads == LOAD_LEVELS["L1"] * 5


# --- metrics + report writer ----------------------------------------------
def test_metrics_summary_math() -> None:
    collector = MetricsCollector()
    for ms in (10, 20, 30, 40, 100):
        collector.record(ActionResult(ActionKind.SEND_URL, True, False, ms / 1000))
    collector.record(ActionResult(ActionKind.SEND_URL, False, True, 0.05))
    summary = collector.summarize(wall_clock_s=1.0)
    assert summary.total == 6
    assert summary.succeeded == 5
    assert summary.failed == 1
    assert summary.blocked == 1
    assert summary.p50_ms > 0
    assert 0 < summary.error_rate < 1


def test_report_writer_appends(tmp_path: Path) -> None:
    target = tmp_path / "PERF.md"
    target.write_text("# header\n", encoding="utf-8")
    writer = ReportWriter(target)
    collector = MetricsCollector()
    collector.record(ActionResult(ActionKind.CLICK_QUALITY, True, False, 0.03))
    writer.performance_entry(
        level="L1",
        profiles="Casual",
        git_sha="abc1234",
        summary=collector.summarize(1.0),
        seed=42,
        transport="stub",
    )
    text = target.read_text(encoding="utf-8")
    assert "# header" in text  # prior content preserved (append-only)
    assert "Load L1" in text
    assert "abc1234" in text
