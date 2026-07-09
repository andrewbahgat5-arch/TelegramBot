"""History inline keyboard (MASTER_PLAN Task 7.4, Sprint 14 Phase 1.3).

Filter buttons (audio/video), numbered item buttons for resend,
prev/next navigation, and a Back/close button.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from bot.callbacks.paging import encode_filter_page
from core.i18n import translate

_FILTER_INDEX = {"audio": 1, "video": 2}


def build_history_keyboard(
    rows: list[Any],
    *,
    page: int,
    has_prev: bool,
    has_next: bool,
    signer: CallbackSigner,
    locale: str,
    format_filter: str | None = None,
    audio_count: int = 0,
    video_count: int = 0,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    current_filter_idx = _FILTER_INDEX.get(format_filter or "", 0)

    audio_label = f"🎧 {translate('history.filter_audio', locale)} · {audio_count}"
    video_label = f"🎥 {translate('history.filter_video', locale)} · {video_count}"
    if format_filter == "audio":
        audio_label = f"✓ {audio_label}"
        audio_target = encode_filter_page(0, 0)
    else:
        audio_target = encode_filter_page(1, 0)
    if format_filter == "video":
        video_label = f"✓ {video_label}"
        video_target = encode_filter_page(0, 0)
    else:
        video_target = encode_filter_page(2, 0)

    builder.row(
        InlineKeyboardButton(
            text=audio_label,
            callback_data=signer.pack_history_page(audio_target),
        ),
        InlineKeyboardButton(
            text=video_label,
            callback_data=signer.pack_history_page(video_target),
        ),
    )

    item_buttons: list[InlineKeyboardButton] = []
    for idx, row in enumerate(rows, start=1):
        item_buttons.append(
            InlineKeyboardButton(
                text=str(idx),
                callback_data=signer.pack_resend(row.id),
            )
        )
    for i in range(0, len(item_buttons), 4):
        builder.row(*item_buttons[i : i + 4])

    nav: list[InlineKeyboardButton] = []
    if has_prev:
        prev_arg = encode_filter_page(current_filter_idx, page - 1)
        nav.append(
            InlineKeyboardButton(
                text=translate("common.prev", locale),
                callback_data=signer.pack_history_page(prev_arg),
            )
        )
    if has_next:
        next_arg = encode_filter_page(current_filter_idx, page + 1)
        nav.append(
            InlineKeyboardButton(
                text=translate("common.next", locale),
                callback_data=signer.pack_history_page(next_arg),
            )
        )
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(
            text=translate("history.close", locale),
            callback_data=signer.pack_history_close(),
        )
    )

    return builder.as_markup()
