"""Telegram ad-delivery adapter (MASTER_PLAN Sprint 9 + 9.5, flow 16.7, Section 8).

Backs ``AdSenderProtocol``: the only place that sends an advertisement for the ad
pipeline. Two paths:

* ``send_ad`` (``fields`` mode) — the ad's ``type`` selects the send method
  (text / photo / video / document / audio / animation), re-using the admin-uploaded
  ``file_id`` (no re-upload), with an optional multi-button inline keyboard and rich
  ``parse_mode``.
* ``copy_ad`` (``copy`` mode, Sprint 9.5) — re-send a stored Telegram message via
  ``copyMessage`` (rich content reproduced without re-upload). ``copyMessage`` drops the
  source's inline keyboard, so the ad's buttons are re-attached here.

Buttons render as Telegram **URL buttons** (``AdButtonSpec.url``) so tapping opens the
destination directly with no extra step (#31). The signed-callback button kind is kept
as a fallback for a future redirect-based tracked mode. ``reply_to_message_id`` attaches
an ad directly under the delivered media (#30).
"""

from __future__ import annotations

from collections.abc import Sequence

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from core.logging import get_logger
from domain.enums import AdType
from domain.protocols.advertising import AdButtonSpec

_log = get_logger("infrastructure.telegram.ad_sender")


class TelegramAdSender:
    """Sends ads via the Telegram Bot API (``AdSenderProtocol``)."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_ad(
        self,
        chat_id: int,
        *,
        ad_type: str,
        text: str | None,
        media_file_id: str | None,
        buttons: Sequence[AdButtonSpec],
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> None:
        markup = _build_markup(buttons)
        rid = reply_to_message_id
        if ad_type == AdType.PHOTO.value and media_file_id is not None:
            await self._bot.send_photo(
                chat_id,
                media_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )
        elif ad_type == AdType.VIDEO.value and media_file_id is not None:
            await self._bot.send_video(
                chat_id,
                media_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )
        elif ad_type == AdType.ANIMATION.value and media_file_id is not None:
            await self._bot.send_animation(
                chat_id,
                media_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )
        elif ad_type == AdType.DOCUMENT.value and media_file_id is not None:
            await self._bot.send_document(
                chat_id,
                media_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )
        elif ad_type == AdType.AUDIO.value and media_file_id is not None:
            await self._bot.send_audio(
                chat_id,
                media_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )
        else:  # text ad (and the defensive fallback when a media id is somehow missing)
            await self._bot.send_message(
                chat_id,
                text or "",
                reply_markup=markup,
                parse_mode=parse_mode,
                reply_to_message_id=rid,
            )

    async def copy_ad(
        self,
        chat_id: int,
        *,
        from_chat_id: int,
        message_id: int,
        buttons: Sequence[AdButtonSpec],
        reply_to_message_id: int | None = None,
    ) -> None:
        await self._bot.copy_message(
            chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            reply_markup=_build_markup(buttons),
            reply_to_message_id=reply_to_message_id,
        )


def _build_markup(buttons: Sequence[AdButtonSpec]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows: dict[int, list[InlineKeyboardButton]] = {}
    for spec in buttons:
        # A URL button opens the destination directly (#31); fall back to a callback
        # button only when no url is set (reserved tracked mode).
        if spec.url:
            button = InlineKeyboardButton(text=spec.text, url=spec.url)
        elif spec.callback_data:
            button = InlineKeyboardButton(text=spec.text, callback_data=spec.callback_data)
        else:
            continue
        rows.setdefault(spec.row, []).append(button)
    keyboard = [rows[row] for row in sorted(rows) if rows[row]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
