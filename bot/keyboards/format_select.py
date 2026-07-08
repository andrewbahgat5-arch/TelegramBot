"""Format-selection inline keyboard (MASTER_PLAN Task 5.7).

One button per format *kind* available for the analyzed media. Tapping it carries a
signed ``(media_id, format)`` callback (Section 14.2) that drives the quality step.
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate
from domain.entities.media import MediaInfo
from domain.enums import MediaFormat
from domain.protocols.advertising import AdButtonSpec

_LABEL_KEYS = {
    MediaFormat.VIDEO: "download.format.video",
    MediaFormat.AUDIO: "download.format.audio",
}


def build_format_keyboard(
    media_id: int, info: MediaInfo, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fmt in (MediaFormat.VIDEO, MediaFormat.AUDIO):
        if any(option.format is fmt for option in info.formats):
            builder.button(
                text=translate(_LABEL_KEYS[fmt], locale),
                callback_data=signer.pack_format(media_id, fmt),
            )
    builder.adjust(1)
    return builder.as_markup()


def append_ad_buttons(
    keyboard: InlineKeyboardMarkup, buttons: Sequence[AdButtonSpec]
) -> InlineKeyboardMarkup:
    """Append a caption ad's CTA buttons as extra rows below the format buttons.

    Grouped by the ad button's ``row`` (mirrors ``build_ad_keyboard`` in the ad transport,
    kept here so the bot layer never imports infrastructure). URL-less rows are skipped.
    """
    if not buttons:
        return keyboard
    rows: dict[int, list[InlineKeyboardButton]] = {}
    for spec in buttons:
        if spec.url:
            btn = InlineKeyboardButton(text=spec.text, url=spec.url)
        elif spec.callback_data:
            btn = InlineKeyboardButton(text=spec.text, callback_data=spec.callback_data)
        else:
            continue
        rows.setdefault(spec.row, []).append(btn)
    ad_rows = [rows[r] for r in sorted(rows) if rows[r]]
    return InlineKeyboardMarkup(inline_keyboard=[*keyboard.inline_keyboard, *ad_rows])
