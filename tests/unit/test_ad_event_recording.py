"""Unit tests for AdService → ad-event recording (MASTER_PLAN Task 9.5.9, D-052).

Verifies that a delivered ad records an impression event and a click records a click
event through the injected recorder — and that recording is best-effort: a delivery
that does not happen (master switch off, premium-exempt) records nothing, and the
counter on the ad row stays the source of truth.
"""

from __future__ import annotations

import datetime

import pytest

from bot.callbacks.factory import CallbackSigner
from services.ad_service import AdService
from services.audience_service import AudienceService
from services.settings_service import SettingsService
from tests.unit._fakes import (
    FakeAdButtonRepo,
    FakeAdRepo,
    FakeAdRow,
    FakeAdSender,
    FakeAudienceRuleRepo,
    FakeCache,
    FakeSegmentMemberRepo,
    FakeSegmentRepo,
    FakeSettingsStore,
)

pytestmark = pytest.mark.asyncio


class _FakeRecorder:
    def __init__(self) -> None:
        self.impressions: list[tuple[int, int | None, str | None]] = []
        self.clicks: list[tuple[int, int | None, int | None]] = []

    def record_impression(
        self, *, advertisement_id: int, user_id: int | None, placement: str | None
    ) -> None:
        self.impressions.append((advertisement_id, user_id, placement))

    def record_click(
        self, *, advertisement_id: int, user_id: int | None, button_id: int | None
    ) -> None:
        self.clicks.append((advertisement_id, user_id, button_id))


def _build(*, ads_enabled: bool = True) -> tuple[AdService, FakeAdRepo, _FakeRecorder]:
    repo = FakeAdRepo()
    recorder = _FakeRecorder()
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true" if ads_enabled else "false", "bool")}),
        FakeCache(),
        cache_ttl=60,
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
        event_recorder=recorder,
    )
    return service, repo, recorder


async def test_delivered_ad_records_impression_with_user_and_placement() -> None:
    service, repo, recorder = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")

    shown = await service.maybe_show(
        chat_id=555,
        role="user",
        is_premium=False,
        premium_expires_at=None,
        total_downloads=1,
        user_row_id=42,
        placement="post_download",
    )

    assert shown is True
    assert repo.by_id[1].impressions == 1  # counter stays authoritative
    assert recorder.impressions == [(1, 42, "post_download")]


async def test_suppressed_ad_records_no_impression() -> None:
    service, repo, recorder = _build(ads_enabled=False)
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")

    shown = await service.maybe_show(
        chat_id=555,
        role="user",
        is_premium=False,
        premium_expires_at=None,
        total_downloads=1,
        user_row_id=42,
    )

    assert shown is False
    assert recorder.impressions == []


async def test_premium_exempt_records_no_impression() -> None:
    service, repo, recorder = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    future = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)

    shown = await service.maybe_show(
        chat_id=555,
        role="user",
        is_premium=True,
        premium_expires_at=future,
        total_downloads=1,
        user_row_id=42,
    )

    assert shown is False
    assert recorder.impressions == []


async def test_record_click_records_click_event() -> None:
    service, repo, recorder = _build()
    repo.by_id[3] = FakeAdRow(id=3, title="C", content_text="hi", button_url="https://x.test")

    url = await service.record_click(3, user_row_id=42)

    assert url == "https://x.test"
    assert repo.by_id[3].clicks == 1  # counter stays authoritative
    assert recorder.clicks == [(3, 42, None)]


async def test_record_click_unknown_ad_records_nothing() -> None:
    service, _repo, recorder = _build()
    assert await service.record_click(999, user_row_id=42) is None
    assert recorder.clicks == []
