"""Unit tests for AudienceService (MASTER_PLAN Sprint 9.5, D-043 truth table)."""

from __future__ import annotations

import pytest

from services.audience_service import AudienceContext, AudienceService
from tests.unit._fakes import (
    FakeAdRow,
    FakeAudienceRuleRepo,
    FakeSegmentMemberRepo,
    FakeSegmentRepo,
)


def _service() -> tuple[AudienceService, FakeAudienceRuleRepo, FakeSegmentMemberRepo]:
    rules = FakeAudienceRuleRepo()
    members = FakeSegmentMemberRepo()
    service = AudienceService(rule_repo=rules, member_repo=members, segment_repo=FakeSegmentRepo())
    return service, rules, members


def _ctx(
    *,
    role: str = "user",
    plan: str = "free",
    language: str | None = "en",
    telegram_id: int = 100,
    user_row_id: int = 1,
    untargeted_exempt: bool = False,
) -> AudienceContext:
    return AudienceContext(
        role=role,
        plan=plan,
        language=language,
        telegram_id=telegram_id,
        user_row_id=user_row_id,
        untargeted_exempt=untargeted_exempt,
    )


async def _rule(rules: FakeAudienceRuleRepo, ad_id: int, effect: str, dim: str, value: str) -> None:
    await rules.create_rule(advertisement_id=ad_id, effect=effect, dimension=dim, value=value)


# --- legacy fallback (no rules) -------------------------------------------
async def test_no_rules_untargeted_shows_to_free() -> None:
    service, _, _ = _service()
    ad = FakeAdRow(id=1, title="A", target_role=None, audience_mode="all")
    assert await service.matches(ad, _ctx()) is True


async def test_no_rules_untargeted_exempts_premium_and_owner() -> None:
    service, _, _ = _service()
    ad = FakeAdRow(id=1, title="A", target_role=None, audience_mode="all")
    assert await service.matches(ad, _ctx(untargeted_exempt=True)) is False


async def test_no_rules_target_role_premium_matches_plan() -> None:
    service, _, _ = _service()
    ad = FakeAdRow(id=1, title="A", target_role="premium", audience_mode="all")
    assert await service.matches(ad, _ctx(plan="premium")) is True
    assert await service.matches(ad, _ctx(plan="free")) is False


# --- include rules --------------------------------------------------------
async def test_include_plan_premium() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "plan", "premium")
    assert await service.matches(ad, _ctx(plan="premium")) is True
    assert await service.matches(ad, _ctx(plan="free")) is False


async def test_include_language_only() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "language", "ar")
    assert await service.matches(ad, _ctx(language="ar")) is True
    assert await service.matches(ad, _ctx(language="en")) is False


async def test_include_explicit_user_ids() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "user_id", "12345")
    await _rule(rules, 1, "include", "user_id", "67890")
    assert await service.matches(ad, _ctx(telegram_id=12345)) is True
    assert await service.matches(ad, _ctx(telegram_id=67890)) is True
    assert await service.matches(ad, _ctx(telegram_id=999)) is False


async def test_include_segment_membership() -> None:
    service, rules, members = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "segment", "7")
    await members.add_member(segment_id=7, user_id=42)
    assert await service.matches(ad, _ctx(user_row_id=42)) is True
    assert await service.matches(ad, _ctx(user_row_id=43)) is False


# --- exclude rules ("all except …") ---------------------------------------
async def test_exclude_premium_shows_to_everyone_else() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="exclude")
    await _rule(rules, 1, "exclude", "plan", "premium")
    assert await service.matches(ad, _ctx(plan="premium")) is False
    assert await service.matches(ad, _ctx(plan="free")) is True


# --- combination semantics ------------------------------------------------
async def test_across_dimensions_is_and() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "plan", "premium")
    await _rule(rules, 1, "include", "language", "ar")
    assert await service.matches(ad, _ctx(plan="premium", language="ar")) is True
    assert await service.matches(ad, _ctx(plan="premium", language="en")) is False
    assert await service.matches(ad, _ctx(plan="free", language="ar")) is False


async def test_within_dimension_is_or() -> None:
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "role", "user")
    await _rule(rules, 1, "include", "role", "owner")
    assert await service.matches(ad, _ctx(role="user")) is True
    assert await service.matches(ad, _ctx(role="owner")) is True
    assert await service.matches(ad, _ctx(role="moderator")) is False


@pytest.mark.parametrize(
    ("plan", "expected"),
    [("premium", True), ("free", False)],
)
async def test_exclude_overrides_include(plan: str, expected: bool) -> None:
    # include premium, but also exclude a specific user: the exclude wins for that user.
    service, rules, _ = _service()
    ad = FakeAdRow(id=1, title="A", audience_mode="include")
    await _rule(rules, 1, "include", "plan", "premium")
    await _rule(rules, 1, "exclude", "user_id", "13")
    assert await service.matches(ad, _ctx(plan=plan, telegram_id=1)) is expected
    assert await service.matches(ad, _ctx(plan="premium", telegram_id=13)) is False
