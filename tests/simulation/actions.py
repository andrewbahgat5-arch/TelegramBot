"""Simulation action vocabulary (MASTER_PLAN §25.15).

A :class:`UserProfile` emits a stream of :class:`SimulatedAction` events; a
:class:`~tests.simulation.bot_client.client.BotClient` performs each and returns
an :class:`ActionResult`. These types are transport-agnostic: the same action
stream drives the deterministic in-memory stub (dry-runs / CI) and, in Phase B,
the real sandbox-bot transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ActionKind(StrEnum):
    """The user interactions the simulator can perform against the bot."""

    START = "start"
    SEND_URL = "send_url"
    CLICK_FORMAT = "click_format"
    CLICK_QUALITY = "click_quality"
    CLICK_RESEND = "click_resend"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class SimulatedAction:
    """One scheduled interaction.

    ``delay_before`` is the realistic think-time (seconds) that precedes the
    action; the runner may honor it (live runs) or compress it (dry-runs).
    ``is_download`` marks the actions that consume a user's download quota — the
    quality click that starts a fresh download, or a resend.
    """

    kind: ActionKind
    delay_before: float = 0.0
    is_download: bool = False
    url: str | None = None
    label: str = ""


@dataclass(frozen=True, slots=True)
class ActionResult:
    """The outcome of performing one action."""

    kind: ActionKind
    success: bool
    blocked: bool
    latency_s: float
    error: str | None = None
