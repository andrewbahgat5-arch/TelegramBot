"""Cookie pool domain types (DESIGN_COOKIE_POOL.md §3, §6).

Pure, framework-free value objects. No I/O, no ORM, no yt-dlp knowledge.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from domain.enums.cookie_health import CookieHealth


class CookieImpact(StrEnum):
    """What an outcome does to a cookie's health.

    The classifier (services/cookie_classifier.py) may only ever return one of these.
    ``NONE`` is the default for anything unrecognised — a false strike removes capacity
    from a healthy pool, while a missed signal costs only slower detection.
    """

    SUCCESS = "success"  # worked; clears the consecutive failure counter
    NONE = "none"  # not the cookie's fault (route, content, unknown) — stats only
    AUTH_FAILURE = "auth_failure"  # session rejected; counts toward cooldown
    EXPIRED = "expired"  # session definitively dead; skip cooldown entirely
    INVALID = "invalid"  # file unusable / account terminated; needs replacement


@dataclass(frozen=True, slots=True)
class CookieVerdict:
    """Classifier output: the health impact plus a short human reason for the audit
    trail and the admin notification."""

    impact: CookieImpact
    reason: str = ""

    @property
    def is_failure(self) -> bool:
        return self.impact is not CookieImpact.SUCCESS

    @property
    def affects_health(self) -> bool:
        """True only for the allowlisted authentication/session signals (§7).

        Route failures (bot-check walls, proxy/WARP/network errors) and content errors
        must return False here — that is the structural guarantee that a bad egress can
        never burn the cookie pool.
        """
        return self.impact in {
            CookieImpact.AUTH_FAILURE,
            CookieImpact.EXPIRED,
            CookieImpact.INVALID,
        }


@dataclass(frozen=True, slots=True)
class CookieSnapshot:
    """Immutable view of a ``youtube_cookies`` row."""

    id: int
    label: str
    status: CookieHealth
    file_version: int
    egress_id: str | None = None
    cooldown_until: datetime.datetime | None = None
    auth_failures: int = 0
    cooldown_cycles: int = 0
    total_uses: int = 0
    total_success: int = 0
    total_auth_failures: int = 0
    total_other_failures: int = 0
    last_used_at: datetime.datetime | None = None
    last_success_at: datetime.datetime | None = None
    last_failure_at: datetime.datetime | None = None
    last_failure_reason: str | None = None

    def is_selectable(self, *, now: datetime.datetime) -> bool:
        """Selectable = a usable status AND no active cooldown (§7)."""
        from domain.enums.cookie_health import SELECTABLE_HEALTH

        if self.status not in SELECTABLE_HEALTH:
            return False
        return self.cooldown_until is None or self.cooldown_until <= now

    @property
    def success_rate(self) -> float | None:
        """Successful requests as a fraction of all requests, or None if never used."""
        total = self.total_success + self.total_auth_failures + self.total_other_failures
        return self.total_success / total if total else None


@dataclass(frozen=True, slots=True)
class CookieEvent:
    """One row of a cookie's audit trail, detached from the ORM session."""

    created_at: datetime.datetime | None
    event: str
    to_status: str | None = None
    reason: str | None = None
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class CookieLease:
    """An exclusive, time-limited claim on one cookie for a single yt-dlp run.

    ``token`` is the Redis lock token required to release it — holding the lease is what
    stops two workers presenting the same Google session simultaneously (§8).
    """

    cookie_id: int
    label: str
    path: Path
    file_version: int
    egress_id: str
    token: str
    probationary: bool = False  # half-open trial after a cooldown
