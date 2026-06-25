"""Integration tests for the Sprint 9 ad SQL (MASTER_PLAN 10.10, flow 16.7).

Exercises the live-DB queries the in-memory fake cannot validate: the role-filtered,
priority-ranked candidate select and the atomic impression/click increments. Auto-skips
when Postgres is unavailable (see conftest).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.models import User
from infrastructure.database.repositories import (
    AdAudienceRuleRepository,
    AdButtonRepository,
    AdRepository,
    AudienceSegmentMemberRepository,
    AudienceSegmentRepository,
    UserRepository,
)

pytestmark = pytest.mark.asyncio


async def _owner(session: AsyncSession, tid: int) -> User:
    return await UserRepository(session).add(User(telegram_id=tid, role="owner"))


async def _ad(session: AsyncSession, owner_id: int) -> int:
    ad = await AdRepository(session).create_ad(
        title="A",
        ad_type="text",
        content_text="hi",
        content_media_file_id=None,
        button_text=None,
        button_url=None,
        target_role=None,
        show_every_n_downloads=1,
        priority=0,
        created_by=owner_id,
    )
    return ad.id


async def test_create_and_increment_counters(db_session: AsyncSession, telegram_id: int) -> None:
    owner = await _owner(db_session, telegram_id)
    repo = AdRepository(db_session)
    ad = await repo.create_ad(
        title="Promo",
        ad_type="text",
        content_text="hello",
        content_media_file_id=None,
        button_text="Shop",
        button_url="https://example.com",
        target_role=None,
        show_every_n_downloads=1,
        priority=0,
        created_by=owner.id,
    )
    assert ad.impressions == 0 and ad.clicks == 0

    await repo.increment_impressions(ad.id)
    await repo.increment_impressions(ad.id)
    await repo.increment_clicks(ad.id)

    refreshed = await repo.get_by_id(ad.id)
    assert refreshed is not None
    assert refreshed.impressions == 2 and refreshed.clicks == 1


async def test_active_candidates_filter_by_role_and_rank_by_priority(
    db_session: AsyncSession, telegram_id: int
) -> None:
    owner = await _owner(db_session, telegram_id)
    repo = AdRepository(db_session)

    async def _ad(
        title: str,
        *,
        priority: int = 0,
        target_role: str | None = None,
        is_active: bool = True,
    ) -> int:
        ad = await repo.create_ad(
            title=title,
            ad_type="text",
            content_text="x",
            content_media_file_id=None,
            button_text=None,
            button_url=None,
            target_role=target_role,
            show_every_n_downloads=1,
            priority=priority,
            created_by=owner.id,
        )
        if not is_active:
            await repo.apply_update(ad, {"is_active": False})
        return ad.id

    low = await _ad("low untargeted", priority=1)
    high = await _ad("high untargeted", priority=9)
    premium = await _ad("premium only", target_role="premium")
    inactive = await _ad("disabled", priority=99, is_active=False)

    free_ids = [a.id for a in await repo.list_active_for_role("user")]
    # Untargeted ads only, highest priority first; the premium-targeted + inactive ones
    # are excluded for a free user.
    assert high in free_ids and low in free_ids
    assert premium not in free_ids and inactive not in free_ids
    assert free_ids.index(high) < free_ids.index(low)

    premium_ids = [a.id for a in await repo.list_active_for_role("premium")]
    assert premium in premium_ids and high in premium_ids


async def test_apply_update_persists_changes(db_session: AsyncSession, telegram_id: int) -> None:
    owner = await _owner(db_session, telegram_id)
    repo = AdRepository(db_session)
    ad = await repo.create_ad(
        title="Old",
        ad_type="text",
        content_text="hi",
        content_media_file_id=None,
        button_text=None,
        button_url=None,
        target_role=None,
        show_every_n_downloads=1,
        priority=0,
        created_by=owner.id,
    )
    await repo.apply_update(ad, {"title": "New", "is_active": False, "priority": 7})
    refreshed = await repo.get_by_id(ad.id)
    assert refreshed is not None
    assert refreshed.title == "New" and refreshed.is_active is False and refreshed.priority == 7


# --- Ads v2 schema (Sprint 9.5) ------------------------------------------
async def test_ad_buttons_crud_and_click_increment(
    db_session: AsyncSession, telegram_id: int
) -> None:
    owner = await _owner(db_session, telegram_id)
    ad_id = await _ad(db_session, owner.id)
    repo = AdButtonRepository(db_session)
    b1 = await repo.create_button(
        advertisement_id=ad_id, text="One", url="https://1", row=0, position=0
    )
    await repo.create_button(advertisement_id=ad_id, text="Two", url="https://2", row=1, position=0)

    rows = await repo.list_for_ad(ad_id)
    assert [r.text for r in rows] == ["One", "Two"]  # keyboard order

    await repo.increment_clicks(b1.id)
    await repo.increment_clicks(b1.id)
    refreshed = await repo.get_by_id(b1.id)
    assert refreshed is not None and refreshed.clicks == 2

    assert await repo.delete_for_ad(ad_id) == 2
    assert list(await repo.list_for_ad(ad_id)) == []


async def test_audience_rules_crud(db_session: AsyncSession, telegram_id: int) -> None:
    owner = await _owner(db_session, telegram_id)
    ad_id = await _ad(db_session, owner.id)
    repo = AdAudienceRuleRepository(db_session)
    await repo.create_rule(
        advertisement_id=ad_id, effect="include", dimension="plan", value="premium"
    )
    await repo.create_rule(
        advertisement_id=ad_id, effect="exclude", dimension="user_id", value="13"
    )

    rules = await repo.list_for_ad(ad_id)
    assert {(r.effect, r.dimension, r.value) for r in rules} == {
        ("include", "plan", "premium"),
        ("exclude", "user_id", "13"),
    }
    assert await repo.delete_for_ad(ad_id) == 2


async def test_audience_segments_and_membership(db_session: AsyncSession, telegram_id: int) -> None:
    owner = await _owner(db_session, telegram_id)
    member = await UserRepository(db_session).add(User(telegram_id=telegram_id + 1, role="user"))
    segments = AudienceSegmentRepository(db_session)
    members = AudienceSegmentMemberRepository(db_session)

    segment = await segments.create_segment(
        name=f"seg{telegram_id}", description=None, created_by=owner.id
    )
    assert await segments.get_by_name(f"seg{telegram_id}") is not None

    assert await members.add_member(segment_id=segment.id, user_id=member.id) is True
    assert await members.add_member(segment_id=segment.id, user_id=member.id) is False  # idempotent
    assert await members.list_segment_ids_for_user(member.id) == {segment.id}
    assert await members.count_members(segment.id) == 1
    assert await members.remove_member(segment_id=segment.id, user_id=member.id) is True
    assert await members.count_members(segment.id) == 0


async def test_broadcast_links_advertisement(db_session: AsyncSession, telegram_id: int) -> None:
    from infrastructure.database.repositories import BroadcastRepository

    owner = await _owner(db_session, telegram_id)
    ad_id = await _ad(db_session, owner.id)
    broadcast = await BroadcastRepository(db_session).create_pending(
        created_by=owner.id,
        message_text="",
        target_language=None,
        target_role=None,
        expected_total=0,
        advertisement_id=ad_id,
    )
    assert broadcast.advertisement_id == ad_id
