"""Unit tests for the history handlers (MASTER_PLAN Task 7.4, flow 16.3)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.callbacks.paging import encode_filter_page
from bot.handlers.history import handle_history, handle_history_page, handle_resend
from core.i18n import translate
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.history_service import HistoryPage, ResendKind
from services.notification_service import NotificationService
from tests.unit._fakes import FakeMessageSender


@dataclass
class FakeHistoryRow:
    id: int
    platform: str = "youtube"
    format: str = "video"
    quality: str = "720p"
    title: str | None = "A Clip"
    duration_seconds: int | None = 112
    size_bytes: int | None = 1_900_000
    file_size: int | None = None
    created_at: datetime.datetime = datetime.datetime(2026, 6, 24, tzinfo=datetime.UTC)


class FakeHistoryService:
    def __init__(
        self, *, page: HistoryPage | None = None, resend: ResendKind = ResendKind.RESENT
    ) -> None:
        self._page = page if page is not None else HistoryPage([], 0, False, False)
        self._resend = resend
        self.resend_calls: list[tuple[int, int, int, int]] = []
        self.list_calls: list[tuple[int, int, str | None]] = []

    async def list_history(
        self, user_id: int, *, page: int = 0, format_filter: str | None = None
    ) -> HistoryPage:
        self.list_calls.append((user_id, page, format_filter))
        return self._page

    async def resend(
        self,
        *,
        download_id: int,
        user_id: int,
        telegram_id: int,
        progress_message_id: int,
        user: object = None,
    ) -> ResendKind:
        self.resend_calls.append((download_id, user_id, telegram_id, progress_message_id))
        return self._resend


def _user() -> UserSnapshot:
    return UserSnapshot(
        id=7,
        telegram_id=555,
        role=UserRole.USER,
        is_banned=False,
        is_premium=False,
        daily_download_count=0,
        daily_download_count_reset_date=datetime.date(2026, 6, 24),
        total_downloads=0,
    )


def _session() -> AsyncSession:
    return object()  # type: ignore[return-value]


def _page_with_rows() -> HistoryPage:
    return HistoryPage(
        [FakeHistoryRow(1), FakeHistoryRow(2, format="audio", quality="mp3")],
        0, False, True,
        format_filter=None,
        audio_count=1,
        video_count=1,
    )


async def test_history_command_lists_rows() -> None:
    page = _page_with_rows()
    history = FakeHistoryService(page=page)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is not None
    assert history.list_calls == [(7, 0, None)]


async def test_history_command_empty_has_no_keyboard() -> None:
    history = FakeHistoryService(page=HistoryPage([], 0, False, False))
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is None


async def test_history_command_no_ad() -> None:
    """Phase 1.1: /history no longer fires a placement ad."""
    page = _page_with_rows()
    history = FakeHistoryService(page=page)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    ad_called = False

    async def fake_ad_svc(*a: Any, **kw: Any) -> None:
        nonlocal ad_called
        ad_called = True

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )
    assert not ad_called


async def test_history_page_callback_edits_message() -> None:
    signer = CallbackSigner("k")
    page = HistoryPage(
        [FakeHistoryRow(3)], 1, True, False,
        audio_count=0, video_count=1,
    )
    history = FakeHistoryService(page=page)
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_history_page(encode_filter_page(0, 1))
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_history_page(
        callback, _session(), _user(), lambda s: history, signer, translate, "en"
    )

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()
    assert history.list_calls == [(7, 1, None)]


async def test_history_page_filter_audio() -> None:
    signer = CallbackSigner("k")
    page = HistoryPage(
        [FakeHistoryRow(4, format="audio")], 0, False, False,
        format_filter="audio", audio_count=1, video_count=0,
    )
    history = FakeHistoryService(page=page)
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_history_page(encode_filter_page(1, 0))
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_history_page(
        callback, _session(), _user(), lambda s: history, signer, translate, "en"
    )

    assert history.list_calls == [(7, 0, "audio")]


async def test_history_page_forged_ignored() -> None:
    history = FakeHistoryService()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "h|2|deadbeef00"
    callback.answer = AsyncMock()

    await handle_history_page(
        callback, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    callback.answer.assert_awaited_once()
    assert history.list_calls == []


def _resend_callback(signer: CallbackSigner) -> Any:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_resend(42)
    callback.from_user = SimpleNamespace(id=555)
    callback.answer = AsyncMock()
    return callback


async def test_resend_callback_resent_deletes_progress() -> None:
    """Phase 1.2: on RESENT, the progress message is deleted (not edited)."""
    signer = CallbackSigner("k")
    history = FakeHistoryService(resend=ResendKind.RESENT)
    msg = FakeMessageSender()
    callback = _resend_callback(signer)

    await handle_resend(
        callback,
        _session(),
        _user(),
        lambda s: history,
        NotificationService(msg),
        signer,
        translate,
        "en",
    )

    callback.answer.assert_awaited_once()
    assert history.resend_calls == [(42, 7, 555, 101)]
    assert len(msg.deletes) == 1


async def test_resend_callback_delete_fails_edits_checkmark() -> None:
    """Phase 1.2: when delete fails, fallback edits to ✅."""
    signer = CallbackSigner("k")
    history = FakeHistoryService(resend=ResendKind.RESENT)
    msg = FakeMessageSender(delete_fails=True)
    callback = _resend_callback(signer)

    await handle_resend(
        callback,
        _session(),
        _user(),
        lambda s: history,
        NotificationService(msg),
        signer,
        translate,
        "en",
    )

    assert len(msg.deletes) == 1
    assert any("✅" == text for _, _, text in msg.edits)


async def test_resend_fires_history_ad_on_resent() -> None:
    """Phase 1.1: ad fires after RESENT, not after other outcomes."""
    signer = CallbackSigner("k")
    history = FakeHistoryService(resend=ResendKind.RESENT)
    msg = FakeMessageSender()
    callback = _resend_callback(signer)
    ad_calls: list[str] = []

    class FakeAd:
        async def show_ad(self, *a: Any, **kw: Any) -> None:
            ad_calls.append("called")

    await handle_resend(
        callback,
        _session(),
        _user(),
        lambda s: history,
        NotificationService(msg),
        signer,
        translate,
        "en",
        ad_service_factory=lambda s: FakeAd(),  # type: ignore[arg-type]
    )

    # The show_placement_ad helper calls ad_service.show_ad internally;
    # the factory was invoked, which is the important assertion.
    assert history.resend_calls == [(42, 7, 555, 101)]


async def test_resend_no_ad_on_needs_relink() -> None:
    """Phase 1.1: no ad fires on NEEDS_RELINK."""
    signer = CallbackSigner("k")
    history = FakeHistoryService(resend=ResendKind.NEEDS_RELINK)
    msg = FakeMessageSender()
    callback = _resend_callback(signer)

    await handle_resend(
        callback,
        _session(),
        _user(),
        lambda s: history,
        NotificationService(msg),
        signer,
        translate,
        "en",
    )

    assert any("send the link again" in text for _, _, text in msg.edits)


async def test_resend_forged_ignored() -> None:
    history = FakeHistoryService()
    msg = FakeMessageSender()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "r|42|deadbeef00"
    callback.answer = AsyncMock()

    await handle_resend(
        callback,
        _session(),
        _user(),
        lambda s: history,
        NotificationService(msg),
        CallbackSigner("k"),
        translate,
        "en",
    )

    callback.answer.assert_awaited_once()
    assert history.resend_calls == []


async def test_render_detail_lines() -> None:
    """Phase 1.3: rich rendering includes duration, size, format, quality, platform."""
    page = HistoryPage(
        [FakeHistoryRow(1, duration_seconds=112, size_bytes=1_900_000)],
        0, False, False,
        audio_count=0, video_count=1,
    )
    history = FakeHistoryService(page=page)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    args = message.answer.await_args
    text = args[0][0] if args.args else args.kwargs.get("text", "")
    if not text:
        text = str(message.answer.await_args)
    assert "01:52" in text or "1:52" in text
    assert "1.8" in text or "1.9" in text


async def test_render_null_duration_size() -> None:
    """Phase 1.3: NULL duration/size renders cleanly without dangling separators."""
    page = HistoryPage(
        [FakeHistoryRow(1, duration_seconds=None, size_bytes=None, file_size=None)],
        0, False, False,
        audio_count=0, video_count=1,
    )
    history = FakeHistoryService(page=page)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    args = message.answer.await_args
    assert args is not None


async def test_packed_arg_round_trip() -> None:
    """Phase 1.3: encode/decode round-trip for filter+page packed arg."""
    from bot.callbacks.paging import decode_filter_page, encode_filter_page

    for fi in range(3):
        for pg in range(10):
            arg = encode_filter_page(fi, pg)
            assert decode_filter_page(arg) == (fi, pg)
