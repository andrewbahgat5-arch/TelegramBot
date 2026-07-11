"""Quality-selection inline keyboard (MASTER_PLAN Task 5.7).

One button per quality available for the chosen format. The button is labelled with
the quality/codec only — the per-quality size is shown in the message description
(``_formats_block`` in the download handler), not on the button. Each carries a signed
``(media_id, format, quality)`` callback.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate
from domain.entities.media import AUDIO_TARGET_BY_QUALITY, MediaFormatOption, MediaInfo
from domain.enums import MediaFormat


def build_quality_keyboard(
    media_id: int, format_: MediaFormat, info: MediaInfo, signer: CallbackSigner, locale: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option in info.formats:
        if option.format is format_:
            builder.button(
                text=_label(option),
                callback_data=signer.pack_quality(media_id, format_, option.quality),
            )
    builder.adjust(2)
    # A Back row returns to the Video/Audio choice without resending the link.
    builder.row(
        InlineKeyboardButton(
            text=translate("common.back", locale), callback_data=signer.pack_back(media_id)
        )
    )
    return builder.as_markup()


def _label(option: MediaFormatOption) -> str:
    """Quality/codec label only — the size lives in the message description now."""
    target = AUDIO_TARGET_BY_QUALITY.get(option.quality)
    return target.label if target is not None else option.quality.value
