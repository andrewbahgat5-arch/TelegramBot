"""Unit tests for the format/quality keyboards (MASTER_PLAN Task 5.7)."""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.format_select import build_format_keyboard
from bot.keyboards.history import build_history_keyboard
from bot.keyboards.quality_select import build_quality_keyboard
from domain.entities.media import MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality

_INFO = MediaInfo(
    platform="youtube",
    video_id="v",
    title="T",
    source_url="https://x/y",
    formats=(
        MediaFormatOption(MediaFormat.VIDEO, Quality.P1080, 5_000_000, "137"),
        MediaFormatOption(MediaFormat.VIDEO, Quality.P720, None, "136"),
        MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 400_000, "140"),
    ),
)


def _buttons(markup: InlineKeyboardMarkup) -> list[InlineKeyboardButton]:
    return [b for row in markup.inline_keyboard for b in row]


def test_format_keyboard_has_one_button_per_kind() -> None:
    signer = CallbackSigner("k")
    buttons = _buttons(build_format_keyboard(5, _INFO, signer, "en"))
    assert len(buttons) == 2  # video + audio
    parsed = signer.unpack(buttons[0].callback_data or "")
    assert parsed is not None and parsed.action == "f" and parsed.media_id == 5


def test_quality_keyboard_lists_qualities_for_format() -> None:
    signer = CallbackSigner("k")
    buttons = _buttons(build_quality_keyboard(5, MediaFormat.VIDEO, _INFO, signer, "en"))
    quality_buttons = [b for b in buttons if (b.callback_data or "").startswith("q|")]
    back_buttons = [b for b in buttons if (b.callback_data or "").startswith("b|")]
    assert len(quality_buttons) == 2  # the two video qualities, not the audio
    assert len(back_buttons) == 1  # a Back row to return to format selection
    labels = [b.text for b in quality_buttons]
    assert any("1080p" in label for label in labels)
    assert any("(~5 MB)" in label for label in labels)  # size shown when known
    parsed = signer.unpack(quality_buttons[0].callback_data or "")
    assert parsed is not None and parsed.action == "q" and parsed.quality is not None
    back = signer.unpack(back_buttons[0].callback_data or "")
    assert back is not None and back.action == "b" and back.media_id == 5


@dataclass
class _HistRow:
    id: int
    platform: str = "youtube"
    format: str = "video"
    quality: str = "720p"
    title: str | None = "A Clip"
    created_at: datetime.datetime = datetime.datetime(2026, 6, 24, tzinfo=datetime.UTC)


def test_history_keyboard_has_resend_button_per_row_and_nav() -> None:
    signer = CallbackSigner("k")
    rows = [_HistRow(1), _HistRow(2)]
    markup = build_history_keyboard(
        rows, page=1, has_prev=True, has_next=True, signer=signer, locale="en"
    )
    buttons = _buttons(markup)
    resend = [b for b in buttons if (b.callback_data or "").startswith("r|")]
    nav = [b for b in buttons if (b.callback_data or "").startswith("h|")]
    assert len(resend) == 2  # one resend per history row
    assert len(nav) == 2  # prev + next
    parsed = signer.unpack(resend[0].callback_data or "")
    assert parsed is not None and parsed.action == "r" and parsed.arg == 1


def test_history_keyboard_first_page_has_no_prev() -> None:
    signer = CallbackSigner("k")
    markup = build_history_keyboard(
        [_HistRow(1)], page=0, has_prev=False, has_next=False, signer=signer, locale="en"
    )
    nav = [b for b in _buttons(markup) if (b.callback_data or "").startswith("h|")]
    assert nav == []  # neither prev nor next on a single full-stop page


def test_quality_label_uses_gb_for_large_files() -> None:
    info = MediaInfo(
        platform="youtube",
        video_id="v",
        title="T",
        source_url="https://x/y",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P2160, 3 * 1024**3, "313"),),
    )
    buttons = _buttons(
        build_quality_keyboard(1, MediaFormat.VIDEO, info, CallbackSigner("k"), "en")
    )
    assert "GB" in buttons[0].text
