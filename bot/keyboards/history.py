"""History inline keyboard (MASTER_PLAN Task 7.4).

One resend button per history row (carrying a signed ``download_id``) plus a
prev/next navigation row. Each row label shows the platform emoji, media title,
and quality (denormalized on ``downloads`` at delivery time).
"""

from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callbacks.factory import CallbackSigner
from core.i18n import translate

_PLATFORM_EMOJI: dict[str, str] = {
    "youtube": "▶️",
    "tiktok": "🎵",
    "instagram": "📸",
    "facebook": "📘",
    "twitter": "🐦",
    "x": "🐦",
    "soundcloud": "🎧",
    "pinterest": "📌",
    "snapchat": "👻",
    "reddit": "🔗",
}


def _platform_emoji(platform: str | None) -> str:
    return _PLATFORM_EMOJI.get((platform or "").lower(), "🔗")


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
    """A one-line label: ``🔁 <platform emoji> <title> · <quality>``."""
    platform_emoji = _platform_emoji(row.platform)
    title = (row.title or row.format)[:35]
    return f"🔁 {platform_emoji} {title} · {row.quality}"
