"""AudienceService (MASTER_PLAN Sprint 9.5, D-043).

Decides whether an ad should be shown to a given user, evaluating the ad's
``audience_mode`` + ``ad_audience_rules`` (first-class targeting), with a backward-
compatible fallback to the Sprint 9 ``target_role`` + global Owner/premium exemption
when an ad has no rules (the D-043 deprecation window).

Rule semantics (LOCKED, §23 Sprint 9.5):
* within a dimension, values are OR-ed;
* across dimensions, dimension-matches are AND-ed;
* an ``exclude`` rule that matches removes the user ("all users except premium").

Segment membership (``audience_segment_members``) is loaded lazily — only when the ad
actually has a ``segment`` rule — so the common case costs no extra query.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from domain.enums import AudienceDimension, AudienceEffect, AudienceMode
from domain.protocols.repositories import (
    AdAudienceRuleRepositoryProtocol,
    AudienceSegmentMemberRepositoryProtocol,
    AudienceSegmentRepositoryProtocol,
)


@dataclass(frozen=True, slots=True)
class AudienceContext:
    """The viewer attributes an audience expression is evaluated against."""

    role: str  # owner / moderator / user
    plan: str  # free / premium (effective plan)
    language: str | None  # BCP-47
    telegram_id: int  # matched by the `user_id` dimension (admin-facing id)
    user_row_id: int  # used for segment-membership lookup
    untargeted_exempt: bool  # premium or role in UNLIMITED_ROLES (legacy exemption)


def evaluate_audience(
    mode: str,
    rules: Sequence[Any],
    ctx: AudienceContext,
    segment_ids: set[int],
) -> bool:
    """Pure audience-rule evaluation — the semantics the SQL compiler must mirror.

    ``mode`` is the expression's ``audience_mode`` (all/include/exclude); ``rules`` are
    its include/exclude rules (ORM rows or :class:`~domain.entities.audience.AudienceRuleSpec`,
    read by ``effect``/``dimension``/``value``); ``segment_ids`` is the viewer's segment
    membership (already loaded). Within a dimension values OR, across dimensions AND, a
    matching ``exclude`` removes the viewer. Kept dependency-free so the SQL compiler
    (``infrastructure.database.audience_query``) can be pinned to it by a shared truth
    table (design invariant #17).
    """
    includes = [r for r in rules if r.effect == AudienceEffect.INCLUDE]
    excludes = [r for r in rules if r.effect == AudienceEffect.EXCLUDE]
    if excludes and _expr_matches(excludes, ctx, segment_ids):
        return False  # explicitly excluded
    if mode == AudienceMode.EXCLUDE:
        return True  # everyone except the (already-checked) exclude expression
    if includes:
        return _expr_matches(includes, ctx, segment_ids)
    return True  # mode 'all' / only exclude rules: show unless excluded


def _expr_matches(rules: Sequence[Any], ctx: AudienceContext, segment_ids: set[int]) -> bool:
    """AND across dimensions, OR within a dimension."""
    by_dimension: dict[str, list[Any]] = {}
    for rule in rules:
        by_dimension.setdefault(rule.dimension, []).append(rule)
    return all(
        any(_rule_hit(rule, ctx, segment_ids) for rule in dim_rules)
        for dim_rules in by_dimension.values()
    )


def _rule_hit(rule: Any, ctx: AudienceContext, segment_ids: set[int]) -> bool:
    dimension, value = rule.dimension, rule.value
    if dimension == AudienceDimension.ROLE:
        return bool(ctx.role == value)
    if dimension == AudienceDimension.PLAN:
        return bool(ctx.plan == value)
    if dimension == AudienceDimension.LANGUAGE:
        return ctx.language is not None and ctx.language == value
    if dimension == AudienceDimension.USER_ID:
        return bool(str(ctx.telegram_id) == value)
    if dimension == AudienceDimension.SEGMENT:
        return bool(value.isdigit() and int(value) in segment_ids)
    return False  # country: reserved, no source yet (EP-20)


class AudienceService:
    def __init__(
        self,
        *,
        rule_repo: AdAudienceRuleRepositoryProtocol[Any],
        member_repo: AudienceSegmentMemberRepositoryProtocol,
        segment_repo: AudienceSegmentRepositoryProtocol[Any] | None = None,
    ) -> None:
        self._rules = rule_repo
        self._members = member_repo
        self._segments = segment_repo

    # --- rule + segment CRUD (admin surface, Task 9.5.5) -----------------
    async def list_rules(self, ad_id: int) -> Sequence[Any]:
        return await self._rules.list_for_ad(ad_id)

    async def add_rule(self, ad_id: int, *, effect: str, dimension: str, value: str) -> Any:
        return await self._rules.create_rule(
            advertisement_id=ad_id, effect=effect, dimension=dimension, value=value
        )

    async def clear_rules(self, ad_id: int) -> int:
        return await self._rules.delete_for_ad(ad_id)

    def _require_segments(self) -> AudienceSegmentRepositoryProtocol[Any]:
        if self._segments is None:  # only the worker delivery path omits it
            raise RuntimeError("segment repository is not wired in this context")
        return self._segments

    async def create_segment(self, *, name: str, description: str | None, created_by: int) -> Any:
        return await self._require_segments().create_segment(
            name=name, description=description, created_by=created_by
        )

    async def find_segment(self, name: str) -> Any | None:
        return await self._require_segments().get_by_name(name)

    async def list_segments(self) -> Sequence[Any]:
        return await self._require_segments().list_all_segments()

    async def add_member(self, *, segment_id: int, user_row_id: int) -> bool:
        return await self._members.add_member(segment_id=segment_id, user_id=user_row_id)

    async def remove_member(self, *, segment_id: int, user_row_id: int) -> bool:
        return await self._members.remove_member(segment_id=segment_id, user_id=user_row_id)

    async def count_members(self, segment_id: int) -> int:
        return await self._members.count_members(segment_id)

    # --- evaluation (delivery, flow 16.7 / D-043) ------------------------
    async def matches(self, ad: Any, ctx: AudienceContext) -> bool:
        """True if ``ad`` should be shown to the user described by ``ctx``."""
        rules = list(await self._rules.list_for_ad(ad.id))
        if not rules:
            return self._legacy_matches(ad, ctx)
        return await self._rule_matches(ad, rules, ctx)

    def _legacy_matches(self, ad: Any, ctx: AudienceContext) -> bool:
        """Sprint 9 behavior for ads with no explicit rules (D-043)."""
        if ad.audience_mode == AudienceMode.INCLUDE:
            return False  # include-mode with no rules targets nobody
        # 'all' (and the degenerate 'exclude' with no rules): apply target_role + exemption.
        effective_role = "premium" if ctx.plan == "premium" else "user"
        if ad.target_role is None:
            return not ctx.untargeted_exempt  # untargeted: premium/Owner are exempt
        return bool(ad.target_role == effective_role)

    async def _rule_matches(self, ad: Any, rules: Sequence[Any], ctx: AudienceContext) -> bool:
        segment_ids = await self._maybe_load_segments(rules, ctx)
        return evaluate_audience(ad.audience_mode, rules, ctx, segment_ids)

    async def _maybe_load_segments(self, rules: Sequence[Any], ctx: AudienceContext) -> set[int]:
        if any(r.dimension == AudienceDimension.SEGMENT for r in rules):
            return await self._members.list_segment_ids_for_user(ctx.user_row_id)
        return set()
