"""Unit tests for the registry-driven wizard engine (Sprint 9.6, D-059)."""

from __future__ import annotations

from bot.panel.registry import audience_option, placement_option
from bot.panel.wizard import (
    STEP_AUDIENCE,
    STEP_CONTENT,
    STEP_PLACEMENT,
    STEP_PREVIEW,
    STEP_SETTINGS,
    STEP_TYPE,
    WizardState,
    applicable_steps,
    first_invalid_step,
    first_step,
    has_step,
    next_step,
    prev_step,
    validate_step,
)


def test_ad_flow_visits_every_step_in_order() -> None:
    ids = [s.step_id for s in applicable_steps("ad")]
    assert ids == [
        STEP_TYPE,
        STEP_AUDIENCE,
        STEP_PLACEMENT,
        STEP_SETTINGS,
        STEP_CONTENT,
        STEP_PREVIEW,
    ]


def test_broadcast_flow_skips_placement() -> None:
    ids = [s.step_id for s in applicable_steps("broadcast")]
    assert STEP_PLACEMENT not in ids
    assert ids == [STEP_TYPE, STEP_AUDIENCE, STEP_SETTINGS, STEP_CONTENT, STEP_PREVIEW]
    assert not has_step("broadcast", STEP_PLACEMENT)


def test_next_and_prev_skip_inapplicable_steps() -> None:
    # Broadcast: Audience -> (skip Placement) -> Settings, and back.
    assert next_step("broadcast", STEP_AUDIENCE) == STEP_SETTINGS
    assert prev_step("broadcast", STEP_SETTINGS) == STEP_AUDIENCE
    # Ad keeps Placement between Audience and Settings.
    assert next_step("ad", STEP_AUDIENCE) == STEP_PLACEMENT
    assert prev_step("ad", STEP_SETTINGS) == STEP_PLACEMENT


def test_first_and_last_step_edges() -> None:
    assert first_step("ad") == STEP_TYPE
    assert prev_step("ad", STEP_TYPE) is None
    assert next_step("ad", STEP_PREVIEW) is None


def test_state_serialization_roundtrip() -> None:
    state = WizardState(
        kind="broadcast",
        step=STEP_SETTINGS,
        audience_mode="include",
        rules=[["include", "plan", "premium"]],
        placements=["video_delivery"],
        priority=5,
        internal_name="Camp",
    )
    restored = WizardState.from_data(state.to_data())
    assert restored == state
    # Unknown keys in stored data are ignored (forward-compatible drafts).
    restored2 = WizardState.from_data({**state.to_data(), "future_field": 1})
    assert restored2 == state


def test_validate_audience_requires_include_rule_in_include_mode() -> None:
    state = WizardState(kind="broadcast", audience_mode="include", rules=[])
    assert validate_step(state, STEP_AUDIENCE) is not None
    state.rules = [["include", "plan", "premium"]]
    assert validate_step(state, STEP_AUDIENCE) is None


def test_validate_audience_flags_contradictory_rules() -> None:
    state = WizardState(
        audience_mode="all",
        rules=[["include", "plan", "premium"], ["exclude", "plan", "premium"]],
    )
    assert validate_step(state, STEP_AUDIENCE) is not None


def test_validate_placement_requires_one_for_ads() -> None:
    state = WizardState(kind="ad", placements=[])
    assert validate_step(state, STEP_PLACEMENT) is not None
    state.placements = ["home"]
    assert validate_step(state, STEP_PLACEMENT) is None


def test_validate_content_modes_and_buttons() -> None:
    state = WizardState(content_mode=None)
    assert validate_step(state, STEP_CONTENT) is not None  # nothing sent yet
    state = WizardState(content_mode="fields", content_text="  ")
    assert validate_step(state, STEP_CONTENT) is not None  # empty text
    state = WizardState(content_mode="copy", storage_message_id=10, storage_chat_id=1)
    assert validate_step(state, STEP_CONTENT) is None
    state.buttons = [["Open", "not-a-url"]]
    assert validate_step(state, STEP_CONTENT) is not None  # bad button url


def test_first_invalid_step_points_at_the_offending_section() -> None:
    # A fresh ad: audience is fine (mode all), but placement + content are incomplete.
    state = WizardState(kind="ad")
    assert first_invalid_step(state) == STEP_PLACEMENT
    state.placements = ["home"]
    assert first_invalid_step(state) == STEP_CONTENT
    state.content_mode = "copy"
    state.storage_chat_id = 1
    state.storage_message_id = 2
    assert first_invalid_step(state) is None


def test_registry_option_lookups() -> None:
    assert audience_option(0) is not None and audience_option(0).effect == "include"
    assert audience_option(999) is None
    assert placement_option(1) is not None and placement_option(1).code == "video_delivery"
    assert placement_option(-1) is None
