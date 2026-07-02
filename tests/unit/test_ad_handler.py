"""Unit tests for the ad handlers (MASTER_PLAN Sprint 9, Tasks 9.2 + 9.4; Sprint 11.5 i18n)."""

from __future__ import annotations

import datetime
from typing import cast
from unittest.mock import AsyncMock

from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import (
    OwnerFilter,
    handle_ad_audience,
    handle_ad_broadcast,
    handle_ad_button_add,
    handle_ad_click,
    handle_ad_create,
    handle_ad_delete,
    handle_ad_disable,
    handle_ad_edit,
    handle_ad_enable,
    handle_ad_global,
    handle_ad_list,
    handle_ad_preview,
    handle_ad_segment_add,
    handle_ad_segment_create,
    handle_ad_segment_list,
    handle_ad_stats,
    handle_ad_toggle,
)
from core.i18n import translate
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.ad_service import AdService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService
from services.settings_service import SettingsService
from services.user_service import UserService
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
    make_cache_service,
)

_EVENT = cast(TelegramObject, object())
_SECRET = "test-secret"
_LOCALE = "en"


def _session() -> AsyncSession:
    return cast(AsyncSession, object())


def _message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    # No attached/replied media by default (text-ad path).
    message.photo = None
    message.video = None
    message.animation = None
    message.reply_to_message = None
    return message


def _answer_text(mock: AsyncMock) -> str:
    args = mock.answer.await_args
    assert args is not None
    return cast(str, args.args[0])


def _owner() -> UserSnapshot:
    return UserSnapshot(
        id=1,
        telegram_id=999,
        role=UserRole.OWNER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 24),
        total_downloads=0,
    )


def _service(repo: FakeAdRepo, *, ads_enabled: bool = True) -> AdService:
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true" if ads_enabled else "false", "bool")}),
        FakeCache(),
        cache_ttl=60,
    )
    return AdService(
        ad_repo=repo,
        settings=settings,
        sender=FakeAdSender(),
        signer=CallbackSigner(_SECRET),
        button_repo=FakeAdButtonRepo(),
        audience=AudienceService(
            rule_repo=FakeAudienceRuleRepo(),
            member_repo=FakeSegmentMemberRepo(),
            segment_repo=FakeSegmentRepo(),
        ),
    )


# --- /ad_create -----------------------------------------------------------
async def test_ad_create_persists_and_confirms() -> None:
    repo = FakeAdRepo()
    message = _message()
    await handle_ad_create(
        message,
        CommandObject(args="title=Sale text=Big sale today every=2"),
        _session(),
        _owner(),
        lambda s: _service(repo),
        translate,
        _LOCALE,
    )
    assert "Created ad #1" in _answer_text(message)
    assert repo.by_id[1].content_text == "Big sale today"
    assert repo.by_id[1].show_every_n_downloads == 2


async def test_ad_create_without_args_shows_usage() -> None:
    message = _message()
    await handle_ad_create(
        message,
        CommandObject(args=None),
        _session(),
        _owner(),
        lambda s: _service(FakeAdRepo()),
        translate,
        _LOCALE,
    )
    assert "Usage" in _answer_text(message)


async def test_ad_create_invalid_reports_error() -> None:
    message = _message()
    await handle_ad_create(
        message,
        CommandObject(args="title=NoContent type=text"),
        _session(),
        _owner(),
        lambda s: _service(FakeAdRepo()),
        translate,
        _LOCALE,
    )
    assert "Cannot create ad" in _answer_text(message)


# --- /ad_list -------------------------------------------------------------
async def test_ad_list_empty() -> None:
    message = _message()
    await handle_ad_list(message, _session(), lambda s: _service(FakeAdRepo()), translate, _LOCALE)
    assert "No ads" in _answer_text(message)


async def test_ad_list_renders_rows() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="Promo", impressions=4, clicks=1)
    message = _message()
    await handle_ad_list(message, _session(), lambda s: _service(repo), translate, _LOCALE)
    text = _answer_text(message)
    assert "Promo" in text and "#1" in text


# --- /ad_edit / toggle / delete -------------------------------------------
async def test_ad_edit_updates() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="Old", content_text="hi")
    message = _message()
    await handle_ad_edit(
        message,
        CommandObject(args="1 title=New"),
        _session(),
        lambda s: _service(repo),
        translate,
        _LOCALE,
    )
    assert "Updated ad #1" in _answer_text(message)
    assert repo.by_id[1].title == "New"


async def test_ad_edit_unknown_id() -> None:
    message = _message()
    await handle_ad_edit(
        message,
        CommandObject(args="9 title=New"),
        _session(),
        lambda s: _service(FakeAdRepo()),
        translate,
        _LOCALE,
    )
    assert "No ad" in _answer_text(message)


async def test_ad_edit_requires_id() -> None:
    message = _message()
    await handle_ad_edit(
        message,
        CommandObject(args=None),
        _session(),
        lambda s: _service(FakeAdRepo()),
        translate,
        _LOCALE,
    )
    assert "Usage" in _answer_text(message)


async def test_ad_toggle_flips() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", is_active=True)
    message = _message()
    await handle_ad_toggle(
        message, CommandObject(args="1"), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    assert "disabled" in _answer_text(message)
    assert repo.by_id[1].is_active is False


async def test_ad_delete_removes() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    message = _message()
    await handle_ad_delete(
        message, CommandObject(args="1"), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    assert "Deleted ad #1" in _answer_text(message)
    assert 1 not in repo.by_id


# --- /ad_stats ------------------------------------------------------------
async def test_ad_stats_overall() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", impressions=10, clicks=5)
    message = _message()
    await handle_ad_stats(
        message, CommandObject(args=None), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    text = _answer_text(message)
    assert "Ad totals" in text and "50.0%" in text  # 5/10 CTR


async def test_ad_stats_single() -> None:
    repo = FakeAdRepo()
    repo.by_id[2] = FakeAdRow(id=2, title="Promo", impressions=4, clicks=1)
    message = _message()
    await handle_ad_stats(
        message, CommandObject(args="2"), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    text = _answer_text(message)
    assert "Ad #2" in text and "Promo" in text


# --- /ad_global -----------------------------------------------------------
async def test_ad_global_off() -> None:
    repo = FakeAdRepo()
    service = _service(repo)
    message = _message()
    await handle_ad_global(
        message,
        CommandObject(args="off"),
        _session(),
        _owner(),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert "OFF" in _answer_text(message)
    assert (
        await service.maybe_show(
            chat_id=1, role="user", is_premium=False, premium_expires_at=None, total_downloads=1
        )
        is False
    )


async def test_ad_global_requires_on_off() -> None:
    message = _message()
    await handle_ad_global(
        message,
        CommandObject(args="maybe"),
        _session(),
        _owner(),
        lambda s: _service(FakeAdRepo()),
        translate,
        _LOCALE,
    )
    assert "Usage" in _answer_text(message)


# --- ad-click callback (Task 9.4) -----------------------------------------
def _callback(data: str) -> AsyncMock:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=Message)
    callback.message.answer = AsyncMock()
    return callback


async def test_ad_click_records_and_delivers_link() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", button_text="Shop", button_url="https://x.test")
    signer = CallbackSigner(_SECRET)
    callback = _callback(signer.pack_ad_click(1))
    await handle_ad_click(
        callback, _session(), _owner(), lambda s: _service(repo), signer, translate, _LOCALE
    )
    assert repo.by_id[1].clicks == 1
    callback.answer.assert_awaited()
    assert "x.test" in _answer_text(callback.message)


async def test_ad_click_forged_payload_is_ignored() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", button_url="https://x.test")
    callback = _callback("a|1|deadbeef00")  # bad signature
    await handle_ad_click(
        callback,
        _session(),
        _owner(),
        lambda s: _service(repo),
        CallbackSigner(_SECRET),
        translate,
        _LOCALE,
    )
    assert repo.by_id[1].clicks == 0
    callback.message.answer.assert_not_awaited()


# --- Sprint 9.5 commands --------------------------------------------------
def _ad_service(
    repo: FakeAdRepo,
    *,
    buttons: FakeAdButtonRepo | None = None,
    sender: FakeAdSender | None = None,
) -> AdService:
    buttons = buttons or FakeAdButtonRepo()
    sender = sender or FakeAdSender()
    settings = SettingsService(
        FakeSettingsStore({"ads_enabled": ("true", "bool")}), FakeCache(), cache_ttl=60
    )
    return AdService(
        ad_repo=repo,
        settings=settings,
        sender=sender,
        signer=CallbackSigner(_SECRET),
        button_repo=buttons,
        audience=AudienceService(
            rule_repo=FakeAudienceRuleRepo(),
            member_repo=FakeSegmentMemberRepo(),
            segment_repo=FakeSegmentRepo(),
        ),
    )


def _audience() -> tuple[AudienceService, FakeAudienceRuleRepo, FakeSegmentMemberRepo]:
    rules = FakeAudienceRuleRepo()
    members = FakeSegmentMemberRepo()
    return (
        AudienceService(rule_repo=rules, member_repo=members, segment_repo=FakeSegmentRepo()),
        rules,
        members,
    )


def _user_service(users: FakeUserRepo) -> UserService:
    cache, _ = make_cache_service()
    return UserService(users, cache, owner_telegram_id=999)


async def test_ad_enable_activates() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", is_active=False)
    message = _message()
    await handle_ad_enable(
        message, CommandObject(args="1"), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    assert repo.by_id[1].is_active is True
    assert "enabled" in _answer_text(message)


async def test_ad_disable_deactivates() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi", is_active=True)
    message = _message()
    await handle_ad_disable(
        message, CommandObject(args="1"), _session(), lambda s: _service(repo), translate, _LOCALE
    )
    assert repo.by_id[1].is_active is False
    assert "disabled" in _answer_text(message)


async def test_ad_preview_delivers() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    sender = FakeAdSender()
    message = _message()
    message.chat = AsyncMock()
    message.chat.id = 999
    await handle_ad_preview(
        message,
        CommandObject(args="1"),
        _session(),
        lambda s: _ad_service(repo, sender=sender),
        translate,
        _LOCALE,
    )
    assert sender.sent and sender.sent[0]["chat_id"] == 999


async def test_ad_audience_sets_mode_and_rules() -> None:
    repo = FakeAdRepo()
    repo.by_id[5] = FakeAdRow(id=5, title="A", content_text="hi")
    audience, rules, _ = _audience()
    message = _message()
    await handle_ad_audience(
        message,
        CommandObject(args="5 include plan:premium lang:ar"),
        _session(),
        lambda s: _service(repo),
        lambda s: audience,
        translate,
        _LOCALE,
    )
    assert repo.by_id[5].audience_mode == "include"
    assert len(await rules.list_for_ad(5)) == 2
    assert "audience set" in _answer_text(message)


async def test_ad_button_add_creates_button() -> None:
    repo = FakeAdRepo()
    repo.by_id[5] = FakeAdRow(id=5, title="A", content_text="hi")
    buttons = FakeAdButtonRepo()
    message = _message()
    await handle_ad_button_add(
        message,
        CommandObject(args="5 Shop now | https://x.test"),
        _session(),
        lambda s: _ad_service(repo, buttons=buttons),
        translate,
        _LOCALE,
    )
    rows = await buttons.list_for_ad(5)
    assert len(rows) == 1 and rows[0].text == "Shop now" and rows[0].url == "https://x.test"


async def test_ad_segment_create_then_add_member() -> None:
    audience, _, members = _audience()
    users = FakeUserRepo()
    users.by_tid[555] = FakeUser(id=7, telegram_id=555)

    create_msg = _message()
    await handle_ad_segment_create(
        create_msg,
        CommandObject(args="vips top users"),
        _session(),
        _owner(),
        lambda s: audience,
        translate,
        _LOCALE,
    )
    segment = await audience.find_segment("vips")
    assert segment is not None and "Created segment" in _answer_text(create_msg)

    add_msg = _message()
    await handle_ad_segment_add(
        add_msg,
        CommandObject(args="vips 555"),
        _session(),
        lambda s: audience,
        lambda s: _user_service(users),
        translate,
        _LOCALE,
    )
    assert (segment.id, 7) in members.members


async def test_ad_segment_list_shows_counts() -> None:
    audience, _, _ = _audience()
    await audience.create_segment(name="vips", description=None, created_by=1)
    message = _message()
    await handle_ad_segment_list(message, _session(), lambda s: audience, translate, _LOCALE)
    assert "vips" in _answer_text(message)


async def test_ad_broadcast_queues_with_ad_link() -> None:
    repo = FakeAdRepo()
    repo.by_id[9] = FakeAdRow(id=9, title="Promo", content_text="hi")
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, role="user", language="en")
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    message = _message()
    await handle_ad_broadcast(
        message,
        CommandObject(args="9 --lang en"),
        _session(),
        _owner(),
        lambda s: _service(repo),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert broadcasts.rows[0].advertisement_id == 9
    assert "broadcast" in _answer_text(message).lower()


async def test_ad_broadcast_with_at_schedules() -> None:
    repo = FakeAdRepo()
    repo.by_id[9] = FakeAdRow(id=9, title="Promo", content_text="hi")
    broadcasts = FakeBroadcastRepo()
    users = FakeUserRepo()
    users.by_tid[1] = FakeUser(id=1, telegram_id=1, role="user", language="en")
    service = BroadcastService(broadcast_repo=broadcasts, user_repo=users)
    message = _message()
    await handle_ad_broadcast(
        message,
        CommandObject(args="9 --at 2026-07-01T12:00:00Z"),
        _session(),
        _owner(),
        lambda s: _service(repo),
        lambda s: service,
        translate,
        _LOCALE,
    )
    assert broadcasts.rows[0].advertisement_id == 9
    assert broadcasts.rows[0].scheduled_at == datetime.datetime(
        2026, 7, 1, 12, 0, tzinfo=datetime.UTC
    )
    assert "scheduled" in _answer_text(message)


async def test_ad_click_per_button_records_button() -> None:
    repo = FakeAdRepo()
    repo.by_id[1] = FakeAdRow(id=1, title="A", content_text="hi")
    buttons = FakeAdButtonRepo()
    button = await buttons.create_button(
        advertisement_id=1, text="Go", url="https://dest", row=0, position=0
    )
    signer = CallbackSigner(_SECRET)
    callback = _callback(signer.pack_ad_click(1, button.id))
    await handle_ad_click(
        callback,
        _session(),
        _owner(),
        lambda s: _ad_service(repo, buttons=buttons),
        signer,
        translate,
        _LOCALE,
    )
    assert buttons.by_id[button.id].clicks == 1
    assert "dest" in _answer_text(callback.message)


# --- authorization --------------------------------------------------------
async def test_owner_filter_blocks_non_owner() -> None:
    # Ad admin commands are owner-only; a moderator (or anyone else) is silently
    # ignored — the filter declines and no handler matches (item #18).
    moderator = UserSnapshot(
        id=2,
        telegram_id=2,
        role=UserRole.MODERATOR,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 24),
        total_downloads=0,
    )
    assert await OwnerFilter(_EVENT, moderator) is False
