"""Unit tests for AdService Ads v2 delivery (MASTER_PLAN Sprint 9.5)."""

from __future__ import annotations

import datetime
from typing import Any

import pytest

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import show_placement_ad
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
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


def _build(
    settings_data: dict[str, tuple[str, str]] | None = None,
    *,
    ad_sender: FakeAdSender | None = None,
) -> tuple[AdService, FakeAdRepo, FakeAdSender, FakeAdButtonRepo, FakeAudienceRuleRepo]:
    repo = FakeAdRepo()
    sender = ad_sender or FakeAdSender()
    buttons = FakeAdButtonRepo()
    rules = FakeAudienceRuleRepo()
    data = {"ads_enabled": ("true", "bool")}
    if settings_data:
        data.update(settings_data)
    settings = SettingsService(FakeSettingsStore(data), FakeCache(), cache_ttl=60)
    audience = AudienceService(
        rule_repo=rules, member_repo=FakeSegmentMemberRepo(), segment_repo=FakeSegmentRepo()
    )
    service = AdService(
        ad_repo=repo,
        settings=settings,
        sender=sender,
        signer=CallbackSigner(_SECRET),
        button_repo=buttons,
        audience=audience,
    )
    return service, repo, sender, buttons, rules


async def _show(service: AdService, **kw: object) -> bool:
    base: dict[str, object] = {
        "chat_id": 555,
        "role": "user",
        "is_premium": False,
        "premium_expires_at": None,
        "total_downloads": 1,
    }
    base.update(kw)
    return await service.maybe_show(**base)  # type: ignore[arg-type]


def _future() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=30)


# --- multi-button rendering (9.5.2 + #31 direct-open) ---------------------
async def test_multiple_buttons_render_as_direct_url_buttons() -> None:
    service, repo, sender, buttons, _ = _build()
    repo.by_id[5] = FakeAdRow(id=5, title="A", content_text="hi")
    await buttons.create_button(advertisement_id=5, text="One", url="https://1", row=0, position=0)
    await buttons.create_button(advertisement_id=5, text="Two", url="https://2", row=1, position=0)

    assert await _show(service) is True
    sent_buttons = sender.sent[0]["buttons"]
    assert [b.text for b in sent_buttons] == ["One", "Two"]
    # Each is a direct-open URL button (#31), carrying its own destination, no callback.
    assert [b.url for b in sent_buttons] == ["https://1", "https://2"]
    assert all(b.callback_data is None for b in sent_buttons)


async def test_url_less_button_is_skipped() -> None:
    service, repo, sender, buttons, _ = _build()
    repo.by_id[5] = FakeAdRow(id=5, title="A", content_text="hi")
    await buttons.create_button(advertisement_id=5, text="No link", url=None, row=0, position=0)
    await _show(service)
    assert sender.sent[0]["buttons"] == []


# --- copy mode (9.5.4) ----------------------------------------------------
async def test_copy_mode_uses_copy_message() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(
        id=1,
        title="Rich",
        type="album",
        delivery_mode="copy",
        storage_chat_id=-1009,
        storage_message_id=42,
    )
    assert await _show(service) is True
    assert sender.sent == []
    assert sender.copied[0]["from_chat_id"] == -1009
    assert sender.copied[0]["message_id"] == 42


# --- rich mode (Rich Markdown via sendRichMessage) ------------------------
async def test_rich_mode_uses_send_rich_message() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(
        id=1, title="Rich", delivery_mode="rich", content_text="# Heading\n- item"
    )
    assert await _show(service) is True
    assert sender.sent == [] and sender.copied == []
    assert sender.rich[0]["markdown"] == "# Heading\n- item"


async def test_rich_mode_falls_back_to_classic_send_when_unsupported() -> None:
    sender = FakeAdSender(rich_error=RuntimeError("bot api lacks rich messages"))
    service, repo, _, _, _ = _build(ad_sender=sender)
    repo.by_id[1] = FakeAdRow(id=1, title="Rich", delivery_mode="rich", content_text="# Heading")
    assert await _show(service) is True  # delivered despite the rich failure
    assert sender.rich == []  # rich attempt raised
    assert sender.sent[0]["ad_type"] == "text" and sender.sent[0]["text"] == "# Heading"


# --- new media types (9.5.3) ----------------------------------------------
async def test_document_ad_dispatches_document() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="Doc", type="document", content_media_file_id="doc-1")
    await _show(service)
    assert sender.sent[0]["ad_type"] == "document"
    assert sender.sent[0]["media_file_id"] == "doc-1"


# --- placement gating (9.5.6) ---------------------------------------------
async def test_placement_disabled_suppresses_ad() -> None:
    service, repo, _, _, _ = _build({"ad_placement_video_delivery_enabled": ("false", "bool")})
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", placement="video_delivery")
    assert await _show(service, placement="video_delivery") is False


async def test_placement_enabled_shows_ad() -> None:
    service, repo, _, _, _ = _build({"ad_placement_video_delivery_enabled": ("true", "bool")})
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", placement="video_delivery")
    assert await _show(service, placement="video_delivery") is True


async def test_only_candidates_for_the_requested_placement_are_considered() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="home", content_text="hi", placement="home")
    # post_download placement (default) has no candidates → nothing shown.
    assert await _show(service) is False
    assert sender.sent == []


# --- audience integration in maybe_show (9.5.5) ---------------------------
async def test_maybe_show_respects_audience_rules() -> None:
    service, repo, _, _, rules = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="Premium", content_text="hi", audience_mode="include")
    await rules.create_rule(advertisement_id=1, effect="include", dimension="plan", value="premium")
    assert await _show(service, is_premium=True, premium_expires_at=_future()) is True
    assert await _show(service) is False  # free user excluded by the rule


# --- preview + per-button click (9.5.2) -----------------------------------
async def test_preview_delivers_regardless_of_frequency() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", show_every_n_downloads=99)
    assert await service.preview(1, chat_id=777) is True
    assert sender.sent[0]["chat_id"] == 777


async def test_record_button_click_increments_button_and_returns_its_url() -> None:
    service, repo, _, buttons, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    button = await buttons.create_button(
        advertisement_id=1, text="Go", url="https://dest", row=0, position=0
    )
    url = await service.record_click(1, button.id)
    assert url == "https://dest"
    assert repo.by_id[1].clicks == 1
    assert buttons.by_id[button.id].clicks == 1


# --- persistent placement hook (9.5.6 — home/history surfaces) -------------
def _user() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=555,
        role=UserRole.USER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 25),
        total_downloads=3,
    )


async def test_placement_hook_delivers_when_enabled() -> None:
    service, repo, sender, _, _ = _build({"ad_placement_home_enabled": ("true", "bool")})
    repo.by_id[1] = FakeAdRow(id=1, title="Home", content_text="hi", placement="home")
    await show_placement_ad(service, _user(), "home")
    assert sender.sent and sender.sent[0]["chat_id"] == 555


async def test_placement_hook_is_noop_when_disabled() -> None:
    service, repo, sender, _, _ = _build()  # home toggle unset → default off
    repo.by_id[1] = FakeAdRow(id=1, title="Home", content_text="hi", placement="home")
    await show_placement_ad(service, _user(), "home")
    assert sender.sent == []


# --- ad attached under the media (#30) ------------------------------------
async def test_reply_to_message_id_is_forwarded_to_the_sender() -> None:
    service, repo, sender, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    await _show(service, reply_to_message_id=4242)
    assert sender.sent[0]["reply_to_message_id"] == 4242


# --- multi-placement + internal metadata (Sprint 9.6, D-056 / D-058) ------
async def test_set_placements_validates_dedupes_and_stores() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    result = await service.set_placements(1, ["video_delivery", "audio_delivery", "video_delivery"])
    assert result == ["video_delivery", "audio_delivery"]  # de-duped, order preserved
    assert await service.list_placements(1) == ["audio_delivery", "video_delivery"]


async def test_set_placements_rejects_unknown_and_empty() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    with pytest.raises(InvalidAdError):
        await service.set_placements(1, ["nowhere"])
    with pytest.raises(InvalidAdError):
        await service.set_placements(1, [])


async def test_set_placements_unknown_ad_returns_none() -> None:
    service, _, _, _, _ = _build()
    assert await service.set_placements(999, ["home"]) is None


async def test_create_stores_internal_metadata() -> None:
    service, repo, _, _, _ = _build()
    ad = await service.create(
        {"title": "Promo", "text": "hi", "internal_name": "Summer Campaign", "notes": "Q3 push"},
        created_by=1,
    )
    assert ad.internal_name == "Summer Campaign"
    assert ad.internal_notes == "Q3 push"


# --- placement-conflict detection (UX sprint #9) --------------------------
async def test_active_conflicts_lists_other_active_ads_on_placement() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="a", placement="post_download")
    repo.by_id[2] = FakeAdRow(id=2, title="B", content_text="b", placement="post_download")
    repo.by_id[3] = FakeAdRow(id=3, title="C", content_text="c", placement="home")
    conflicts = await service.active_conflicts("post_download", exclude_id=1)
    assert [ad.id for ad in conflicts] == [2]  # ad 1 excluded, ad 3 is a different placement


async def test_targets_placement_uses_rows_then_column() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="a", placement="post_download")
    assert await service.targets_placement(1, "post_download") is True
    await repo.set_placements(1, ["home", "history"])  # placement rows win over the column
    assert await service.targets_placement(1, "post_download") is False
    assert await service.targets_placement(1, "home") is True


async def test_replace_active_on_placement_disables_the_others() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="Keep", content_text="k", placement="post_download")
    repo.by_id[2] = FakeAdRow(id=2, title="Old", content_text="o", placement="post_download")
    disabled = await service.replace_active_on_placement("post_download", keep_id=1)
    assert disabled == [2]
    assert repo.by_id[2].is_active is False
    assert repo.by_id[1].is_active is True  # the kept ad is untouched


# --- caption layer (two-layer ads) ----------------------------------------
async def _select_caption(service: AdService, **kw: Any) -> Any:
    base: dict[str, Any] = {
        "role": "user",
        "is_premium": False,
        "premium_expires_at": None,
        "total_downloads": 1,
    }
    base.update(kw)
    return await service.select_caption_ad(**base)


async def test_select_caption_ad_returns_text_and_records_impression() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(
        id=1, title="C", content_text="Subscribe!", placement="caption", show_every_n_downloads=1
    )
    ad = await _select_caption(service)
    assert ad is not None and ad.text == "Subscribe!"
    assert repo.by_id[1].impressions == 1  # counter + rotation advanced
    assert repo.by_id[1].last_shown_at is not None


async def test_select_caption_ad_none_when_only_post_download_ads() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="P", content_text="hi", placement="post_download")
    assert await _select_caption(service) is None


async def test_select_caption_ad_none_for_owner_on_untargeted() -> None:
    # An untargeted (audience=all) ad is exempt for the owner — same rule as the follow-up.
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="C", content_text="hi", placement="caption")
    assert await _select_caption(service, role="owner") is None


async def test_select_caption_ad_respects_every_n() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(
        id=1, title="C", content_text="hi", placement="caption", show_every_n_downloads=2
    )
    assert await _select_caption(service, total_downloads=1) is None  # not due
    assert await _select_caption(service, total_downloads=2) is not None  # due


async def test_select_caption_ad_skips_ad_with_no_text() -> None:
    service, repo, _, _, _ = _build()
    repo.by_id[1] = FakeAdRow(id=1, title="C", content_text=None, placement="caption")
    assert await _select_caption(service) is None
