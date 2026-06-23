"""Unit tests for the format/quality keyboards (MASTER_PLAN Task 5.7)."""

from __future__ import annotations

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


def _buttons(markup: object) -> list[object]:
    return [b for row in markup.inline_keyboard for b in row]  # type: ignore[attr-defined]


def test_format_keyboard_has_one_button_per_kind() -> None:
    signer = CallbackSigner("k")
    buttons = _buttons(build_format_keyboard(5, _INFO, signer))
    assert len(buttons) == 2  # video + audio
    parsed = signer.unpack(buttons[0].callback_data or "")  # type: ignore[attr-defined]
    assert parsed is not None and parsed.action == "f" and parsed.media_id == 5


def test_quality_keyboard_lists_qualities_for_format() -> None:
    signer = CallbackSigner("k")
    buttons = _buttons(build_quality_keyboard(5, MediaFormat.VIDEO, _INFO, signer))
    assert len(buttons) == 2  # the two video qualities, not the audio
    labels = [b.text for b in buttons]  # type: ignore[attr-defined]
    assert any("1080p" in label for label in labels)
    assert any("(~5 MB)" in label for label in labels)  # size shown when known
    parsed = signer.unpack(buttons[0].callback_data or "")  # type: ignore[attr-defined]
    assert parsed is not None and parsed.action == "q" and parsed.quality is not None


def test_quality_label_uses_gb_for_large_files() -> None:
    info = MediaInfo(
        platform="youtube",
        video_id="v",
        title="T",
        source_url="https://x/y",
        formats=(MediaFormatOption(MediaFormat.VIDEO, Quality.P2160, 3 * 1024**3, "313"),),
    )
    buttons = _buttons(build_quality_keyboard(1, MediaFormat.VIDEO, info, CallbackSigner("k")))
    assert "GB" in buttons[0].text  # type: ignore[attr-defined]
