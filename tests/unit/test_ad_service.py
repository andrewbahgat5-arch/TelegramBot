"""Unit tests for AdService (MASTER_PLAN Sprint 9, flow 16.7 — LOCKED D-010)."""

from __future__ import annotations

import datetime

import pytest

from bot.callbacks.factory import CallbackSigner
from services.ad_service import AdService, InvalidAdError
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

_SECRET = "test-secret"


def _audience() -> AudienceService:
    return AudienceService(
        rule_repo=FakeAudienceRuleRepo(),
        member_repo=FakeSegmentMemberRepo(),
        segment_repo=FakeSegmentRepo(),
    )


def _build(*, ads_enabled: bool = True) -> tuple[AdService, FakeAdRepo, FakeAdSender]:
    repo = FakeAdRepo()
    sender = FakeAdSender()
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true" if ads_enabled else "false", "bool")}),
        FakeCache(),
        cache_ttl=60,
    )
    service = AdService(
        ad_repo=repo,
        settings=settings,
        sender=sender,
        signer=CallbackSigner(_SECRET),
        button_repo=FakeAdButtonRepo(),
        audience=_audience(),
    )
    return service, repo, sender


def _future() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)


async def _show(
    service: AdService,
    *,
    role: str = "user",
    is_premium: bool = False,
    premium_expires_at: datetime.datetime | None = None,
    total: int = 1,
    chat_id: int = 555,
) -> bool:
    return await service.maybe_show(
        chat_id=chat_id,
        role=role,
        is_premium=is_premium,
        premium_expires_at=premium_expires_at,
        total_downloads=total,
    )


# --- master switch --------------------------------------------------------
async def test_master_switch_off_suppresses_all_ads() -> None:
    service, repo, sender = _build(ads_enabled=False)
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    assert await _show(service) is False
    assert sender.sent == []
    assert repo.by_id[1].impressions == 0


async def test_untargeted_ad_shown_to_free_user_increments_impression() -> None:
    service, repo, sender = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    assert await _show(service) is True
    assert len(sender.sent) == 1
    assert repo.by_id[1].impressions == 1


# --- premium / owner exemption (16.7 step 4) ------------------------------
async def test_premium_user_does_not_see_untargeted_ad() -> None:
    service, repo, sender = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    shown = await _show(service, is_premium=True, premium_expires_at=_future())
    assert shown is False
    assert repo.by_id[1].impressions == 0


async def test_owner_is_exempt_from_untargeted_ads_like_premium() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    assert await _show(service, role="owner") is False
    assert repo.by_id[1].impressions == 0


async def test_expired_premium_grant_falls_back_to_free_and_sees_ad() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    assert await _show(service, is_premium=True, premium_expires_at=past) is True


# --- role targeting (16.7 step 3) -----------------------------------------
async def test_premium_targeted_ad_shows_to_premium_only() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="P", content_text="hi", target_role="premium")
    assert await _show(service, is_premium=True, premium_expires_at=_future()) is True
    repo.by_id[1].impressions = 0
    assert await _show(service) is False  # free user: role mismatch


async def test_user_targeted_ad_shows_to_free_user() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="U", content_text="hi", target_role="user")
    assert await _show(service) is True


# --- frequency (post-increment modulo, D-010) -----------------------------
@pytest.mark.parametrize(
    ("total", "expected"),
    [(1, False), (2, False), (3, True), (4, False), (6, True)],
)
async def test_frequency_modulo_is_post_increment(total: int, expected: bool) -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", show_every_n_downloads=3)
    assert await _show(service, total=total) is expected


# --- priority + fall-through ----------------------------------------------
async def test_highest_priority_candidate_wins() -> None:
    service, repo, sender = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="low", content_text="lo", priority=5)
    repo.by_id[2] = FakeAdRow(id=2, title="high", content_text="hi", priority=10)
    assert await _show(service) is True
    assert repo.by_id[2].impressions == 1
    assert repo.by_id[1].impressions == 0


async def test_frequency_miss_falls_through_to_next_candidate() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(
        id=1, title="high", content_text="hi", priority=10, show_every_n_downloads=2
    )
    repo.by_id[2] = FakeAdRow(
        id=2, title="low", content_text="lo", priority=5, show_every_n_downloads=1
    )
    assert await _show(service, total=1) is True  # high misses (1%2), low wins
    assert repo.by_id[2].impressions == 1
    assert repo.by_id[1].impressions == 0


# --- delivery shape + click button ----------------------------------------
async def test_button_ad_renders_a_direct_url_button() -> None:
    service, repo, sender = _build()
    repo.by_id[7] = FakeAdRow(
        id=7,
        title="Promo",
        type="photo",
        content_text="caption",
        content_media_file_id="file-123",
        button_text="Shop",
        button_url="https://example.com",
    )
    assert await _show(service) is True
    sent = sender.sent[0]
    assert sent["ad_type"] == "photo" and sent["media_file_id"] == "file-123"
    assert len(sent["buttons"]) == 1
    button = sent["buttons"][0]
    # Direct-open URL button (#31): the destination is the url, no callback.
    assert button.text == "Shop" and button.url == "https://example.com"
    assert button.callback_data is None


async def test_ad_without_button_has_no_keyboard() -> None:
    service, repo, sender = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    await _show(service)
    assert sender.sent[0]["buttons"] == []


async def test_send_failure_is_swallowed_and_skips_impression() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true", "bool")}), FakeCache(), cache_ttl=60
    )
    service = AdService(
        ad_repo=repo,
        settings=settings,
        sender=FakeAdSender(error=RuntimeError("telegram down")),
        signer=CallbackSigner(_SECRET),
        button_repo=FakeAdButtonRepo(),
        audience=_audience(),
    )
    assert await _show(service) is False
    assert repo.by_id[1].impressions == 0  # not counted on a failed send


# --- click tracking (16.7 W6) ---------------------------------------------
async def test_record_click_increments_and_returns_url() -> None:
    service, repo, _ = _build()
    repo.by_id[3] = FakeAdRow(id=3, title="A", button_url="https://x")
    url = await service.record_click(3)
    assert url == "https://x"
    assert repo.by_id[3].clicks == 1


async def test_record_click_unknown_id_is_noop() -> None:
    service, _, _ = _build()
    assert await service.record_click(999) is None


# --- create validation (Task 9.2) -----------------------------------------
async def test_create_text_ad_persists_fields() -> None:
    service, repo, _ = _build()
    ad = await service.create(
        {"title": "Sale", "type": "text", "text": "Big sale", "every": "3", "priority": "5"},
        created_by=1,
    )
    assert ad.title == "Sale" and ad.content_text == "Big sale"
    assert ad.show_every_n_downloads == 3 and ad.priority == 5


async def test_create_uses_default_frequency_when_omitted() -> None:
    service, _, _ = _build()
    ad = await service.create({"title": "A", "text": "hi"}, created_by=1, default_frequency=4)
    assert ad.show_every_n_downloads == 4


async def test_create_media_ad_uses_attached_file_id() -> None:
    service, _, _ = _build()
    ad = await service.create(
        {"title": "Promo", "type": "video"}, created_by=1, media_file_id="vid-1"
    )
    assert ad.content_media_file_id == "vid-1" and ad.type == "video"


@pytest.mark.parametrize(
    "fields",
    [
        {"text": "no title"},
        {"title": "x", "type": "bogus", "text": "hi"},
        {"title": "x", "type": "text"},  # text ad without text
        {"title": "x", "type": "photo"},  # media ad without file_id
        {"title": "x", "text": "hi", "button_text": "Go"},  # button missing url
        {"title": "x", "text": "hi", "target": "moderator"},  # invalid target
        {"title": "x", "text": "hi", "every": "0"},  # below minimum
        {"title": "x", "text": "hi", "bogus": "1"},  # unknown field
    ],
)
async def test_create_rejects_invalid(fields: dict[str, str]) -> None:
    service, _, _ = _build()
    with pytest.raises(InvalidAdError):
        await service.create(fields, created_by=1)


# --- edit / toggle / delete -----------------------------------------------
async def test_edit_applies_changes() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="Old", content_text="hi", priority=0)
    ad = await service.edit(1, {"title": "New", "priority": "9"})
    assert ad is not None and ad.title == "New" and ad.priority == 9


async def test_edit_unknown_id_returns_none() -> None:
    service, _, _ = _build()
    assert await service.edit(404, {"title": "x"}) is None


async def test_edit_clearing_text_on_text_ad_is_rejected() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    with pytest.raises(InvalidAdError):
        await service.edit(1, {"text": ""})


async def test_edit_empty_change_set_is_rejected() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    with pytest.raises(InvalidAdError):
        await service.edit(1, {})


async def test_toggle_flips_active_state() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", is_active=True)
    result = await service.toggle(1)
    assert result is not None and result[1] is False
    assert repo.by_id[1].is_active is False


async def test_delete_removes_ad() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    assert await service.delete(1) is True
    assert await service.delete(1) is False


# --- stats + global switch ------------------------------------------------
async def test_overall_stats_aggregates_counters() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", impressions=10, clicks=2, is_active=True)
    repo.by_id[2] = FakeAdRow(id=2, title="B", impressions=5, clicks=1, is_active=False)
    stats = await service.overall_stats()
    assert stats.total_ads == 2 and stats.active_ads == 1
    assert stats.impressions == 15 and stats.clicks == 3


async def test_detailed_stats_returns_dataclass() -> None:
    service, repo, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", impressions=10, clicks=2, is_active=True)
    stats = await service.detailed_stats(1)
    assert stats is not None
    assert stats.title == "A"
    assert stats.impressions_total == 10
    assert stats.clicks_total == 2
    assert stats.ctr == "20.0%"
    assert stats.impressions_by_placement == {}


async def test_detailed_stats_not_found() -> None:
    service, _, _ = _build()
    assert await service.detailed_stats(999) is None


async def test_set_global_writes_master_switch() -> None:
    repo = FakeAdRepo()
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true", "bool")}), FakeCache(), cache_ttl=60
    )
    service = AdService(
        ad_repo=repo,
        settings=settings,
        sender=FakeAdSender(),
        signer=CallbackSigner(_SECRET),
        button_repo=FakeAdButtonRepo(),
        audience=_audience(),
    )
    await service.set_global(False, updated_by=1)
    assert await settings.get("ads_enabled") is False
