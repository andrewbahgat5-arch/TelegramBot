"""Unit tests for the pure audience evaluator (Sprint 9.6, F-2 / EP-22).

Anchors ``services.audience_service.evaluate_audience`` to the shared truth table
(``tests/audience_cases.py``) with hand-computed expectations. The integration test
``tests/integration/test_audience_query.py`` then proves the SQL compiler agrees with
this same evaluator over real rows (design invariant #17).
"""

from __future__ import annotations

import pytest

from domain.entities.audience import AudienceRuleSpec
from domain.enums import AudienceDimension, AudienceEffect, AudienceMode
from services.audience_service import evaluate_audience
from tests.audience_cases import NOW, SCENARIOS, USERS, Scenario, ctx_for


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_python_matcher_truth_table(scenario: Scenario) -> None:
    selected = {
        user.key
        for user in USERS
        if evaluate_audience(scenario.mode, list(scenario.rules), ctx_for(user, NOW), set())
    }
    assert selected == set(scenario.expected_keys)


def test_segment_inclusion_matches_members_only() -> None:
    """A ``segment`` include targets exactly the users in that segment."""
    rule = AudienceRuleSpec(AudienceEffect.INCLUDE.value, AudienceDimension.SEGMENT.value, "5")
    members = {"prem_en", "free_ar"}
    selected = {
        user.key
        for user in USERS
        if evaluate_audience(
            AudienceMode.INCLUDE.value,
            [rule],
            ctx_for(user, NOW),
            {5} if user.key in members else set(),
        )
    }
    assert selected == members


def test_non_numeric_segment_value_never_matches() -> None:
    rule = AudienceRuleSpec(
        AudienceEffect.INCLUDE.value, AudienceDimension.SEGMENT.value, "not-a-number"
    )
    user = USERS[0]
    assert not evaluate_audience(AudienceMode.INCLUDE.value, [rule], ctx_for(user, NOW), {5})
