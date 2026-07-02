"""History inline keyboard (MASTER_PLAN Task 7.4).

One resend button per history row (carrying a signed ``download_id``) plus a
prev/next navigation row. The richer browsable surface the Owner described
(thumbnails, titles) is a future sprint — V1 lists the denormalized
platform/format/quality/date that ``downloads`` already stores.
"""

from __future__ import annotations

import datetime
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate


def build_history_keyboard(
    rows: list[Any],
    *,
    page: int,
    has_prev: bool,
    has_next: bool,
    signer: CallbackSigner,
    locale: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for row in rows:
        builder.row(
            InlineKeyboardButton(text=_row_label(row), callback_data=signer.pack_resend(row.id))
        )
    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(
            InlineKeyboardButton(
                text=translate("common.prev", locale),
                callback_data=signer.pack_history_page(page - 1),
            )
        )
    if has_next:
        nav.append(
            InlineKeyboardButton(
                text=translate("common.next", locale),
                callback_data=signer.pack_history_page(page + 1),
            )
        )
    if nav:
        builder.row(*nav)
    return builder.as_markup()


def _row_label(row: Any) -> str:
    """A one-line label: ``🔁 <Platform> · <quality> · <date>``."""
    platform = (row.platform or "link").capitalize()
    when = _short_date(row.created_at)
    return f"🔁 {platform} · {row.quality} · {when}"


def _short_date(value: datetime.datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")
