"""Shared audience truth table (Sprint 9.6, F-2 / EP-22, design invariant #17).

A single set of users + targeting scenarios used by *both* evaluators so they can never
drift (``DESIGN_9.6_unified_audience_wizard.md`` §6):

* ``tests/unit/test_audience_evaluator.py`` runs the **Python matcher**
  (``services.audience_service.evaluate_audience``) against ``expected_keys``;
* ``tests/integration/test_audience_query.py`` seeds these users in Postgres and asserts
  the **SQL compiler** (``infrastructure.database.audience_query``) selects the same set.

Segment targeting is exercised separately (its rule value is a DB-assigned id), not in
this static table.
"""

from __future__ import annotations

import dataclasses
import datetime

from domain.entities.audience import AudienceRuleSpec
from domain.enums import AudienceDimension, AudienceEffect, AudienceMode
from services.audience_service import AudienceContext

NOW = datetime.datetime(2026, 6, 27, 12, 0, tzinfo=datetime.UTC)
_EXPIRED = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)


@dataclasses.dataclass(frozen=True)
class UserAttrs:
    """Enough of a ``users`` row to build an :class:`AudienceContext` or seed the DB."""

    key: str
    telegram_id: int
    role: str
    is_premium: bool
    premium_expires_at: datetime.datetime | None
    language: str | None


# Effective plan @ NOW: prem_en + owner = premium; prem_expired = free (grant lapsed).
USERS: tuple[UserAttrs, ...] = (
    UserAttrs("free_en", 990001, "user", False, None, "en"),
    UserAttrs("prem_en", 990002, "user", True, None, "en"),
    UserAttrs("prem_expired", 990003, "user", True, _EXPIRED, "ar"),
    UserAttrs("free_ar", 990004, "user", False, None, "ar"),
    UserAttrs("mod_en", 990005, "moderator", False, None, "en"),
    UserAttrs("owner", 990006, "owner", True, None, None),
)


def is_premium_active(user: UserAttrs, now: datetime.datetime) -> bool:
    return user.is_premium and (user.premium_expires_at is None or user.premium_expires_at > now)


def ctx_for(
    user: UserAttrs, now: datetime.datetime, segment_ids: set[int] | None = None
) -> AudienceContext:
    """Build the matcher's viewer context, computing the effective plan like delivery does."""
    return AudienceContext(
        role=user.role,
        plan="premium" if is_premium_active(user, now) else "free",
        language=user.language,
        telegram_id=user.telegram_id,
        user_row_id=user.telegram_id,  # the truth table keys segment membership by tid
        untargeted_exempt=False,
    )


def _inc(dimension: str, value: str) -> AudienceRuleSpec:
    return AudienceRuleSpec(AudienceEffect.INCLUDE.value, dimension, value)


def _exc(dimension: str, value: str) -> AudienceRuleSpec:
    return AudienceRuleSpec(AudienceEffect.EXCLUDE.value, dimension, value)


_ROLE = AudienceDimension.ROLE.value
_PLAN = AudienceDimension.PLAN.value
_LANG = AudienceDimension.LANGUAGE.value
_UID = AudienceDimension.USER_ID.value
_COUNTRY = AudienceDimension.COUNTRY.value


@dataclasses.dataclass(frozen=True)
class Scenario:
    name: str
    mode: str
    rules: tuple[AudienceRuleSpec, ...]
    expected_keys: frozenset[str]


ALL = AudienceMode.ALL.value
INCLUDE = AudienceMode.INCLUDE.value
EXCLUDE = AudienceMode.EXCLUDE.value

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "all_no_rules",
        ALL,
        (),
        frozenset({"free_en", "prem_en", "prem_expired", "free_ar", "mod_en", "owner"}),
    ),
    Scenario(
        "include_premium", INCLUDE, (_inc(_PLAN, "premium"),), frozenset({"prem_en", "owner"})
    ),
    Scenario(
        "exclude_premium",
        EXCLUDE,
        (_exc(_PLAN, "premium"),),
        frozenset({"free_en", "prem_expired", "free_ar", "mod_en"}),
    ),
    Scenario(
        "include_free",
        INCLUDE,
        (_inc(_PLAN, "free"),),
        frozenset({"free_en", "prem_expired", "free_ar", "mod_en"}),
    ),
    Scenario(
        "include_user_and_premium",
        INCLUDE,
        (_inc(_ROLE, "user"), _inc(_PLAN, "premium")),
        frozenset({"prem_en"}),
    ),
    Scenario(
        "include_lang_en_or_ar",
        INCLUDE,
        (_inc(_LANG, "en"), _inc(_LANG, "ar")),
        frozenset({"free_en", "prem_en", "prem_expired", "free_ar", "mod_en"}),
    ),
    Scenario("include_user_id", INCLUDE, (_inc(_UID, "990004"),), frozenset({"free_ar"})),
    Scenario(
        "exclude_user_id_from_all",
        ALL,
        (_exc(_UID, "990001"),),
        frozenset({"prem_en", "prem_expired", "free_ar", "mod_en", "owner"}),
    ),
    Scenario(
        "include_premium_exclude_lang_ar",
        INCLUDE,
        (_inc(_PLAN, "premium"), _exc(_LANG, "ar")),
        frozenset({"prem_en", "owner"}),
    ),
    Scenario("include_country_yields_none", INCLUDE, (_inc(_COUNTRY, "US"),), frozenset()),
)
