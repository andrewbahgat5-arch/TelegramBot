"""Unit tests for the format/quality keyboards (MASTER_PLAN Task 5.7)."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.format_select import build_format_keyboard
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
    buttons = _buttons(build_format_keyboard(5, _INFO, signer))
    assert len(buttons) == 2  # video + audio
    parsed = signer.unpack(buttons[0].callback_data or "")
    assert parsed is not None and parsed.action == "f" and parsed.media_id == 5


def test_quality_keyboard_lists_qualities_for_format() -> None:
    signer = CallbackSigner("k")
    buttons = _buttons(build_quality_keyboard(5, MediaFormat.VIDEO, _INFO, signer))
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


def test_quality_label_uses_gb_for_large_files() -> None:
    info = MediaInfo(
        platform="youtube",
        video_id="v",
        title="T",
        source_url="https://x/y",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P2160, 3 * 1024**3, "313"),),
    )
    buttons = _buttons(build_quality_keyboard(1, MediaFormat.VIDEO, info, CallbackSigner("k")))
    assert "GB" in buttons[0].text
