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
    created_at: datetime.datetime = datetime.datetime(2026, 6, 24, tzinfo=datetime.UTC)


class FakeHistoryService:
    def __init__(
        self, *, page: HistoryPage | None = None, resend: ResendKind = ResendKind.RESENT
    ) -> None:
        self._page = page if page is not None else HistoryPage([], 0, False, False)
        self._resend = resend
        self.resend_calls: list[tuple[int, int, int, int]] = []
        self.list_calls: list[tuple[int, int]] = []

    async def list_history(self, user_id: int, *, page: int = 0) -> HistoryPage:
        self.list_calls.append((user_id, page))
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
    return object()  # type: ignore[return-value]  # factory ignores it


async def test_history_command_lists_rows() -> None:
    page = HistoryPage([FakeHistoryRow(1), FakeHistoryRow(2)], 0, False, True)
    history = FakeHistoryService(page=page)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is not None
    assert history.list_calls == [(7, 0)]


async def test_history_command_empty_has_no_keyboard() -> None:
    history = FakeHistoryService(page=HistoryPage([], 0, False, False))
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()

    await handle_history(
        message, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is None


async def test_history_page_callback_edits_message() -> None:
    signer = CallbackSigner("k")
    page = HistoryPage([FakeHistoryRow(3)], 1, True, False)
    history = FakeHistoryService(page=page)
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_history_page(1)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_history_page(
        callback, _session(), _user(), lambda s: history, signer, translate, "en"
    )

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()
    assert history.list_calls == [(7, 1)]


async def test_history_page_forged_ignored() -> None:
    history = FakeHistoryService()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "h|2|deadbeef00"  # bad signature
    callback.answer = AsyncMock()

    await handle_history_page(
        callback, _session(), _user(), lambda s: history, CallbackSigner("k"), translate, "en"
    )

    callback.answer.assert_awaited_once()
    assert history.list_calls == []  # forged never reaches the service


def _resend_callback(signer: CallbackSigner) -> Any:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_resend(42)
    callback.from_user = SimpleNamespace(id=555)
    callback.answer = AsyncMock()
    return callback


async def test_resend_callback_resent_marks_completed() -> None:
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
    # send_initial mints message id 101 (FakeMessageSender starts at 100); resend gets it.
    assert history.resend_calls == [(42, 7, 555, 101)]
    # The progress message is edited to the completed text.
    assert any("Done" in text for _, _, text in msg.edits)


async def test_resend_callback_needs_relink_message() -> None:
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
    callback.data = "r|42|deadbeef00"  # bad signature
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
