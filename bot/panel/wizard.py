"""Registry-driven compose wizard engine (Sprint 9.6, F-2 / EP-22, D-059).

One engine drives both the Ad and Broadcast creation flows over a **registry of step
objects** — never hardcoded transitions (``DESIGN_9.6_unified_audience_wizard.md`` §4.10).
A step declares which wizard kinds it applies to, so the engine computes the applicable
next/previous step (Broadcast auto-skips Placement). The same engine powers the
edit-from-preview hub (jump to a step, return to Preview) and the §4.9 pre-save
validation. Adding Scheduling / Country / A-B / … later is registering one more step.

This module is intentionally pure (no aiogram, no DB, no signer): the in-progress
:class:`WizardState` is a JSON-serializable payload (so a future "save/resume draft" is
additive — Owner #15) and every function here is unit-testable in isolation. Rendering
(keyboards) and persistence live in the keyboard/handler layers.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

WizardKind = Literal["ad", "broadcast"]

# Step ids (also the ``arg`` carried in a signed "go to step" callback — kept tiny).
# There is deliberately no "Type" step: the wizard's ``kind`` (Ad vs Broadcast) is fixed
# by the section the admin entered from (Advertisements → ad, Broadcast → broadcast), so
# the admin is never asked to choose it again (UX sprint #1/#2).
STEP_AUDIENCE = "audience"
STEP_PLACEMENT = "placement"
STEP_SETTINGS = "settings"
STEP_CONTENT = "content"
STEP_PREVIEW = "preview"


@dataclass(frozen=True, slots=True)
class Step:
    """One wizard step. ``applies_to`` is the set of kinds that include it."""

    step_id: str
    title: str
    applies_to: frozenset[str]


# Ordered registry. Placement is ads-only, so Broadcast skips it; Preview is the hub.
# Steps are *registered* here — a new step (Scheduling / Country / A-B / …) is inserted
# into this tuple with no change to the engine (D-059). The flow starts at Audience: the
# wizard kind is decided by the entry section, so there is no "Type" step (UX sprint #1).
_BOTH = frozenset({"ad", "broadcast"})
_ADS = frozenset({"ad"})
STEPS: tuple[Step, ...] = (
    Step(STEP_AUDIENCE, "Audience", _BOTH),
    Step(STEP_PLACEMENT, "Placement", _ADS),
    # Settings (Enabled / Priority / Every-N / internal name) only apply to a persistent ad;
    # a one-shot broadcast has no on/off or priority, so it skips this step (UX sprint #11).
    Step(STEP_SETTINGS, "Settings", _ADS),
    Step(STEP_CONTENT, "Content", _BOTH),
    Step(STEP_PREVIEW, "Preview", _BOTH),
)
_STEP_INDEX = {step.step_id: i for i, step in enumerate(STEPS)}


@dataclass
class WizardState:
    """The in-progress composition (JSON-serializable for FSM storage / future drafts)."""

    kind: WizardKind = "ad"
    step: str = STEP_AUDIENCE
    return_to: str = "flow"  # "flow" (first pass) or "preview" (edit-hub)
    # Language-first flow: the Broadcast/Ad menu's language pick seeds this before the
    # wizard opens (never re-asked). NULL = untargeted (legacy behavior).
    target_language: str | None = None
    # Preview's two save actions (Publish vs Save-for-later): set True by the "pb" callback
    # just before Save runs, so the same save path can create a "pending" (sent) or "draft"
    # (not sent) broadcast without duplicating the audience/content assembly.
    publish: bool = False
    audience_mode: str = "all"
    rules: list[list[str]] = field(default_factory=list)  # [effect, dimension, value]
    placements: list[str] = field(default_factory=list)
    enabled: bool = True
    priority: int = 0
    frequency: int = 1
    internal_name: str | None = None
    internal_notes: str | None = None
    # Content (copy mode = a stored message; fields mode = composed text).
    content_mode: str | None = None  # "copy" | "fields"
    content_text: str | None = None  # HTML rendering (broadcast send / fallback)
    content_markdown: str | None = None  # raw Rich-Markdown source (ad rich-message send)
    storage_chat_id: int | None = None
    storage_message_id: int | None = None
    buttons: list[list[str]] = field(default_factory=list)  # [text, url]
    # The panel message being edited in place, and the target id when editing an ad.
    chat_id: int | None = None
    message_id: int | None = None
    editing_ad_id: int | None = None
    # Cached audience size shown on the Preview step (#7); recomputed on each entry, so it
    # is transient UI state rather than part of the composition.
    estimated_recipients: int | None = None
    # Post-download conflict resolution (#9): set once the admin has answered the "already
    # active" warning on Save, so it is asked at most once. ``conflict_replace`` records the
    # Replace choice (disable the other active post-download ads on save).
    conflict_ack: bool = False
    conflict_replace: bool = False

    def to_data(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "step": self.step,
            "return_to": self.return_to,
            "target_language": self.target_language,
            "publish": self.publish,
            "audience_mode": self.audience_mode,
            "rules": self.rules,
            "placements": self.placements,
            "enabled": self.enabled,
            "priority": self.priority,
            "frequency": self.frequency,
            "internal_name": self.internal_name,
            "internal_notes": self.internal_notes,
            "content_mode": self.content_mode,
            "content_text": self.content_text,
            "content_markdown": self.content_markdown,
            "storage_chat_id": self.storage_chat_id,
            "storage_message_id": self.storage_message_id,
            "buttons": self.buttons,
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "editing_ad_id": self.editing_ad_id,
            "estimated_recipients": self.estimated_recipients,
            "conflict_ack": self.conflict_ack,
            "conflict_replace": self.conflict_replace,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> WizardState:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def applicable_steps(kind: str) -> list[Step]:
    return [step for step in STEPS if kind in step.applies_to]


def first_step(kind: str) -> str:
    return applicable_steps(kind)[0].step_id


def next_step(kind: str, step_id: str) -> str | None:
    """The next applicable step after ``step_id``, or None at the end (Preview)."""
    seq = applicable_steps(kind)
    ids = [s.step_id for s in seq]
    if step_id not in ids:
        return None
    idx = ids.index(step_id)
    return ids[idx + 1] if idx + 1 < len(ids) else None


def prev_step(kind: str, step_id: str) -> str | None:
    """The previous applicable step before ``step_id``, or None at the first step."""
    seq = applicable_steps(kind)
    ids = [s.step_id for s in seq]
    if step_id not in ids:
        return None
    idx = ids.index(step_id)
    return ids[idx - 1] if idx > 0 else None


def step_index(step_id: str) -> int:
    return _STEP_INDEX.get(step_id, -1)


def step_at(index: int | None) -> str | None:
    """The step id at registry ``index`` (the compact callback ``arg``), or None."""
    if index is not None and 0 <= index < len(STEPS):
        return STEPS[index].step_id
    return None


def has_step(kind: str, step_id: str) -> bool:
    return any(s.step_id == step_id for s in applicable_steps(kind))


# --- validation (§4.9 — each error names its step, so the hub can jump there) ---
def validate_step(state: WizardState, step_id: str) -> str | None:
    """Return a human error for ``step_id`` given ``state``, or None when it's complete."""
    if step_id == STEP_AUDIENCE:
        if state.audience_mode == "include" and not _has_effect(state.rules, "include"):
            return "Add at least one Include rule, or switch the mode to All."
        for dimension, value in _contradictions(state.rules):
            return f"Rule {dimension}={value} is both included and excluded."
        return None
    if step_id == STEP_PLACEMENT:
        if state.kind == "ad" and not state.placements:
            return "Pick at least one placement."
        return None
    if step_id == STEP_CONTENT:
        if state.content_mode is None:
            return "Send the advertisement content."
        if state.content_mode == "fields" and not (state.content_text or "").strip():
            return "Add the message text."
        if state.content_mode == "copy" and state.storage_message_id is None:
            return "Forward or send the message to use as content."
        for _text, url in state.buttons:
            if not _looks_like_url(url):
                return f"Button URL is not valid: {url}"
        return None
    return None


def first_invalid_step(state: WizardState) -> str | None:
    """The first applicable step (excluding Preview) that fails validation, if any."""
    for step in applicable_steps(state.kind):
        if step.step_id == STEP_PREVIEW:
            continue
        if validate_step(state, step.step_id) is not None:
            return step.step_id
    return None


def _has_effect(rules: Sequence[Sequence[str]], effect: str) -> bool:
    return any(rule[0] == effect for rule in rules)


def _contradictions(rules: Sequence[Sequence[str]]) -> list[tuple[str, str]]:
    includes = {(d, v) for e, d, v in rules if e == "include"}
    excludes = {(d, v) for e, d, v in rules if e == "exclude"}
    return sorted(includes & excludes)


def _looks_like_url(url: str) -> bool:
    return url.startswith(("http://", "https://", "tg://")) and len(url) > 8
