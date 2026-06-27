"""Unit tests for the stress-scenario catalog (MASTER_PLAN Task 11.9, §25.15.6)."""

from __future__ import annotations

import random

from tests.simulation.scenarios import STRESS_SCENARIOS, ScenarioCatalog


def _rng(seed: int) -> random.Random:
    return random.Random(seed)  # noqa: S311 - deterministic test data, not crypto


def test_catalog_has_all_six_scenarios() -> None:
    assert ScenarioCatalog.ids() == ["ST-1", "ST-2", "ST-3", "ST-4", "ST-5", "ST-6"]
    assert len(STRESS_SCENARIOS) == 6


def test_every_scenario_has_expected_behavior() -> None:
    for scenario in STRESS_SCENARIOS:
        assert scenario.expected_behavior.strip()
        assert scenario.kind in {"load", "fault"}
        assert scenario.requires_live_infra is True


def test_get_unknown_scenario_raises() -> None:
    try:
        ScenarioCatalog.get("ST-99")
    except KeyError as exc:
        assert "unknown stress scenario" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_load_scenarios_build_deterministic_plans() -> None:
    load = [s for s in STRESS_SCENARIOS if s.kind == "load"]
    assert {s.id for s in load} == {"ST-1", "ST-2"}
    for scenario in load:
        assert scenario.plan_builder is not None
        first = scenario.plan_builder(_rng(1))
        second = scenario.plan_builder(_rng(1))
        assert len(first) == len(second) > 0
        assert [s.user_id for s in first] == [s.user_id for s in second]


def test_st1_models_thousand_user_spike() -> None:
    plan = ScenarioCatalog.get("ST-1").plan_builder(_rng(2))  # type: ignore[misc]
    assert len(plan) == 1000


def test_st2_models_five_thousand_flood() -> None:
    plan = ScenarioCatalog.get("ST-2").plan_builder(_rng(3))  # type: ignore[misc]
    assert len(plan) == 5000


def test_fault_scenarios_have_no_plan_builder() -> None:
    fault = [s for s in STRESS_SCENARIOS if s.kind == "fault"]
    assert {s.id for s in fault} == {"ST-3", "ST-4", "ST-5", "ST-6"}
    assert all(s.plan_builder is None for s in fault)
