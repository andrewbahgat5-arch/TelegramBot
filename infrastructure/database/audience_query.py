"""Set-based audience evaluator: compile audience rules into a SQL predicate.

See ``DESIGN_9.6_unified_audience_wizard.md`` (Sprint 9.6, F-2 / EP-22). The broadcast
count/paging path must select an audience of *many* users in SQL, unlike the per-viewer
Python matcher (``services.audience_service.evaluate_audience``) that judges one user at
a time on the ad-delivery hot path. Both implement the **same** semantics — within a
dimension values OR, across dimensions AND, a matching ``exclude`` removes the user,
``mode`` ∈ all/include/exclude — and are pinned to one another by a shared truth table
(design invariant #17, ``tests/integration/test_audience_query.py``).

Pure infrastructure: builds SQLAlchemy predicates over ``User`` and never imports
``services`` (Section 8). ``compile_audience_predicate`` is the core — bit-for-bit
identical to the Python matcher (invariant #17). ``broadcast_audience_predicate`` wraps
it with the default broadcast guards (exclude banned / staff), kept separate so the core
never drifts from the matcher.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from sqlalchemy import and_, false, or_, select, true
from sqlalchemy.sql.elements import ColumnElement

from domain.entities.audience import AudienceRuleSpec
from domain.enums import AudienceDimension, AudienceEffect, AudienceMode
from infrastructure.database.models import User
from infrastructure.database.models.audience_segment import AudienceSegmentMember

_STAFF_ROLES = ("owner", "moderator")


def broadcast_audience_predicate(
    mode: str,
    rules: Sequence[AudienceRuleSpec],
    *,
    now: datetime.datetime,
) -> ColumnElement[bool]:
    """The audience core predicate plus the broadcast default guards (design §9.4).

    Never message **banned** users, and never message **staff** (owner/moderator) unless
    an explicit ``include role=<staff>`` rule names that role. The guards live only here —
    ``compile_audience_predicate`` stays identical to the Python matcher (invariant #17).
    """
    included_staff = {
        rule.value
        for rule in rules
        if rule.effect == AudienceEffect.INCLUDE
        and rule.dimension == AudienceDimension.ROLE
        and rule.value in _STAFF_ROLES
    }
    excluded_staff = [role for role in _STAFF_ROLES if role not in included_staff]
    guards: list[ColumnElement[bool]] = [User.is_banned.is_(False)]
    if excluded_staff:
        guards.append(User.role.notin_(excluded_staff))
    return and_(compile_audience_predicate(mode, rules, now=now), *guards)


def compile_audience_predicate(
    mode: str,
    rules: Sequence[AudienceRuleSpec],
    *,
    now: datetime.datetime,
) -> ColumnElement[bool]:
    """Compile ``(mode, rules)`` into a boolean predicate over ``User``.

    Mirrors ``services.audience_service.evaluate_audience``:
    membership = ``NOT(exclude-expr matches)`` AND ``(mode==exclude OR no-includes OR
    include-expr matches)``. ``now`` resolves the effective-premium predicate (premium ⇔
    ``is_premium`` and an unexpired grant), matching the matcher's ``ctx.plan``.
    """
    includes = [r for r in rules if r.effect == AudienceEffect.INCLUDE]
    excludes = [r for r in rules if r.effect == AudienceEffect.EXCLUDE]
    clauses: list[ColumnElement[bool]] = []
    if excludes:  # NOT (matches the exclude expression)
        clauses.append(~_expr_predicate(excludes, now))
    if mode != AudienceMode.EXCLUDE and includes:
        clauses.append(_expr_predicate(includes, now))
    if not clauses:
        return true()
    return and_(*clauses)


def _expr_predicate(
    rules: Sequence[AudienceRuleSpec], now: datetime.datetime
) -> ColumnElement[bool]:
    """AND across dimensions, OR within a dimension."""
    by_dimension: dict[str, list[AudienceRuleSpec]] = {}
    for rule in rules:
        by_dimension.setdefault(rule.dimension, []).append(rule)
    dim_clauses = [
        or_(*[_rule_predicate(rule, now) for rule in dim_rules])
        for dim_rules in by_dimension.values()
    ]
    if not dim_clauses:
        return true()
    return and_(*dim_clauses)


def _rule_predicate(rule: AudienceRuleSpec, now: datetime.datetime) -> ColumnElement[bool]:
    dimension, value = rule.dimension, rule.value
    if dimension == AudienceDimension.ROLE:
        return User.role == value
    if dimension == AudienceDimension.PLAN:
        premium = and_(
            User.is_premium.is_(True),
            or_(User.premium_expires_at.is_(None), User.premium_expires_at > now),
        )
        if value == "premium":
            return premium
        if value == "free":
            return ~premium
        return false()
    if dimension == AudienceDimension.LANGUAGE:
        # NULL-safe: a NULL language must read as "does not match" (definite FALSE), so
        # that under an exclude's NOT(...) it flips to TRUE — matching the Python matcher's
        # ``ctx.language is not None and ctx.language == value`` (SQL's NULL != value is
        # NULL, and NOT NULL is NULL, which would wrongly drop NULL-language users).
        return and_(User.language.is_not(None), User.language == value)
    if dimension == AudienceDimension.USER_ID:
        if not value.lstrip("-").isdigit():
            return false()
        return User.telegram_id == int(value)
    if dimension == AudienceDimension.SEGMENT:
        if not value.isdigit():
            return false()
        return User.id.in_(
            select(AudienceSegmentMember.user_id).where(
                AudienceSegmentMember.segment_id == int(value)
            )
        )
    return false()  # country: reserved (EP-20)
