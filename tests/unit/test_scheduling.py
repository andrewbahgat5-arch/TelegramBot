"""Unit tests for ad/broadcast scheduling (MASTER_PLAN Task 9.5.10, D-053).

Covers the service-level behavior: the AdService placement gate (a future-scheduled ad
is not shown until due) and the `scheduled_at` field on ad create/edit, plus
BroadcastService threading `scheduled_at` into the durable row that the worker's
due-poller reads.
"""

from __future__ import annotations

import datetime

import pytest

from bot.callbacks.factory import CallbackSigner
from services.ad_service import AdService, InvalidAdError
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService
from services.settings_service import SettingsService
from tests.unit._fakes import (
    FakeAdButtonRepo,
    FakeAdRepo,
    FakeAdRow,
    FakeAdSender,
    FakeAudienceRuleRepo,
    FakeBroadcastRepo,
    FakeCache,
    FakeSegmentMemberRepo,
    FakeSegmentRepo,
    FakeSettingsStore,
    FakeUser,
    FakeUserRepo,
)

pytestmark = pytest.mark.asyncio


def _ad_service() -> tuple[AdService, FakeAdRepo]:
    repo = FakeAdRepo()
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true", "bool")}), FakeCache(), cache_ttl=60
    )
    service = AdService(
        ad_repo=repo,
        settings=settings,
        sender=FakeAdSender(),
        signer=CallbackSigner("test-secret"),
        button_repo=FakeAdButtonRepo(),
        audience=AudienceService(
            rule_repo=FakeAudienceRuleRepo(),
            member_repo=FakeSegmentMemberRepo(),
            segment_repo=FakeSegmentRepo(),
        ),
    )
    return service, repo


async def _show(service: AdService) -> bool:
    return await service.maybe_show(
        chat_id=555,
        role="user",
        is_premium=False,
        premium_expires_at=None,
        total_downloads=1,
    )


# --- AdService placement gate ---------------------------------------------


async def test_future_scheduled_ad_is_not_shown() -> None:
    service, repo = _ad_service()
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", scheduled_at=future)
    assert await _show(service) is False
    assert repo.by_id[1].impressions == 0


async def test_past_scheduled_ad_is_shown() -> None:
    service, repo = _ad_service()
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=1)
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", scheduled_at=past)
    assert await _show(service) is True


async def test_unscheduled_ad_is_shown() -> None:
    service, repo = _ad_service()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    assert await _show(service) is True


# --- AdService scheduled_at field on create/edit --------------------------


async def test_create_parses_scheduled_at_field() -> None:
    service, _repo = _ad_service()
    ad = await service.create(
        {"title": "A", "text": "hi", "scheduled_at": "2026-07-01T12:00:00Z"},
        created_by=1,
    )
    assert ad.scheduled_at == datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)


async def test_create_rejects_bad_scheduled_at() -> None:
    service, _repo = _ad_service()
    with pytest.raises(InvalidAdError):
        await service.create({"title": "A", "text": "hi", "scheduled_at": "soon"}, created_by=1)


async def test_edit_can_clear_scheduled_at() -> None:
    service, repo = _ad_service()
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", scheduled_at=future)
    updated = await service.edit(1, {"scheduled_at": "none"})
    assert updated is not None and updated.scheduled_at is None


# --- BroadcastService threads scheduled_at --------------------------------


def _broadcast_service() -> tuple[BroadcastService, FakeBroadcastRepo]:
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, role="user")
    return BroadcastService(broadcast_repo=broadcasts, user_repo=users), broadcasts


async def test_broadcast_create_persists_scheduled_at() -> None:
    service, broadcasts = _broadcast_service()
    when = datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)
    await service.create(created_by_user_id=1, message_text="hi", scheduled_at=when)
    assert broadcasts.rows[0].scheduled_at == when


async def test_ad_broadcast_create_persists_scheduled_at() -> None:
    service, broadcasts = _broadcast_service()
    when = datetime.datetime(2026, 7, 1, 12, 0, tzinfo=datetime.UTC)
    await service.create_from_ad(created_by_user_id=1, advertisement_id=9, scheduled_at=when)
    assert broadcasts.rows[0].scheduled_at == when
    assert broadcasts.rows[0].advertisement_id == 9
