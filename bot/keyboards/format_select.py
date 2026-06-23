"""Format-selection inline keyboard (MASTER_PLAN Task 5.7).

One button per format *kind* available for the analyzed media. Tapping it carries a
signed ``(media_id, format)`` callback (Section 14.2) that drives the quality step.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from domain.entities.media import MediaInfo
from domain.enums import MediaFormat

_LABELS = {MediaFormat.VIDEO: "🎬 Video", MediaFormat.AUDIO: "🎵 Audio"}


def build_format_keyboard(
    media_id: int, info: MediaInfo, signer: CallbackSigner
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fmt in (MediaFormat.VIDEO, MediaFormat.AUDIO):
        if any(option.format is fmt for option in info.formats):
            builder.button(text=_LABELS[fmt], callback_data=signer.pack_format(media_id, fmt))
    builder.adjust(1)
    return builder.as_markup()
