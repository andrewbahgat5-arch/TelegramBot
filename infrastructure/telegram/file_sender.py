"""Telegram file + message adapters (MASTER_PLAN Task 6.3, Section 7.1).

The only place that sends Telegram files/messages for the download pipeline. Two
adapters back the domain ports:

* :class:`TelegramFileSender` (``FileSenderProtocol``) — the worker **uploads the
  file once to the requesting user** (that send *is* their delivery) and captures
  the reusable ``file_id``; any additional waiters (fan-out, Sprint 7) are served by
  that ``file_id`` via :meth:`send_cached`. Uploading straight to the user avoids the
  earlier "upload to a storage chat, then re-send" pattern that delivered the file
  twice when the requester was the storage owner.
* :class:`TelegramMessageSender` (``MessageSenderProtocol``) — the raw message
  transport ``NotificationService`` uses for progress edits.

Audio containers Telegram would otherwise convert to a **voice note** (``ogg``,
``opus``) — or does not render as music (``flac``) — are sent as **documents** so the
user gets a real, reusable audio file. ``mp3``/``m4a``/``aac``/``wav`` are sent as
audio (inline player). The send method is chosen deterministically from
``(format, quality)`` so :meth:`upload` and :meth:`send_cached` always agree, keeping
the cached ``file_id`` valid.

The ``Bot`` is built by the composition root; when ``BOT_API_BASE_URL`` is set it
points at the self-hosted Bot API server (2 GB cap, D-040).
"""

from __future__ import annotations

from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, Message

from core.logging import get_logger
from domain.enums import MediaFormat, Quality
from domain.exceptions import CachedFileExpiredError, TelegramUploadError
from domain.protocols.file_sender import UploadedFile

_log = get_logger("infrastructure.telegram.file_sender")

# Audio containers sent as documents (Telegram turns ogg/opus into voice notes and
# does not render flac as music). Everything else audio goes via send_audio.
_AUDIO_AS_DOCUMENT = frozenset({"ogg", "opus", "flac"})

# Telegram rejection fragments that mean "this file_id is not valid for me" — a
# file_id from a different bot/API server, or one Telegram has expired.
_INVALID_FILE_ID_MARKERS = ("file identifier", "wrong remote file", "wrong file_id", "wrong url")


def _audio_is_document(quality: Quality) -> bool:
    return quality.value in _AUDIO_AS_DOCUMENT


def _is_invalid_file_id(exc: TelegramBadRequest) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _INVALID_FILE_ID_MARKERS)


class TelegramFileSender:
    """Uploads and delivers files via the Telegram Bot API (``FileSenderProtocol``)."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def upload(
        self,
        path: Path,
        *,
        format_: MediaFormat,
        quality: Quality,
        chat_id: int,
        filename: str,
        caption: str | None = None,
    ) -> UploadedFile:
        """Upload ``path`` to ``chat_id`` (delivering it) and return its reusable ids."""
        media = FSInputFile(path, filename=filename)
        try:
            message = await self._send(
                chat_id, media, format_=format_, quality=quality, caption=caption
            )
        except Exception as exc:  # aiogram/network failure → domain error
            raise TelegramUploadError("Uploading the file to Telegram failed.") from exc
        return _extract_upload(message)

    async def send_cached(
        self,
        telegram_id: int,
        file_id: str,
        *,
        format_: MediaFormat,
        quality: Quality,
        caption: str | None = None,
    ) -> int | None:
        """Deliver an already-uploaded file to a user by ``file_id`` (16.2 / fan-out)."""
        try:
            message = await self._send(
                telegram_id, file_id, format_=format_, quality=quality, caption=caption
            )
        except TelegramBadRequest as exc:
            if _is_invalid_file_id(exc):
                # Stale/foreign file_id → signal the caller to evict + re-download.
                raise CachedFileExpiredError(str(exc)) from exc
            raise TelegramUploadError("Delivering the file to the user failed.") from exc
        except Exception as exc:
            raise TelegramUploadError("Delivering the file to the user failed.") from exc
        return message.message_id

    async def _send(
        self,
        chat_id: int,
        media: FSInputFile | str,
        *,
        format_: MediaFormat,
        quality: Quality,
        caption: str | None,
    ) -> Message:
        if format_ is MediaFormat.VIDEO:
            return await self._bot.send_video(
                chat_id, media, caption=caption, supports_streaming=True
            )
        if format_ is MediaFormat.AUDIO and not _audio_is_document(quality):
            return await self._bot.send_audio(chat_id, media, caption=caption)
        return await self._bot.send_document(chat_id, media, caption=caption)


class TelegramMessageSender:
    """Plain text send/edit transport for ``NotificationService``."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, text: str) -> int:
        message = await self._bot.send_message(chat_id, text)
        return message.message_id

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> None:
        try:
            await self._bot.edit_message_text(text, chat_id=chat_id, message_id=message_id)
        except TelegramBadRequest as exc:
            # "message is not modified" / message deleted by the user — non-fatal.
            _log.debug("progress_edit_skipped", chat_id=chat_id, error=str(exc))


def _extract_upload(message: Message) -> UploadedFile:
    media = message.video or message.audio or message.document or message.voice
    if media is None:  # pragma: no cover - defensive; a send always returns media
        raise TelegramUploadError("Telegram returned no file reference.")
    return UploadedFile(
        file_id=media.file_id,
        unique_file_id=media.file_unique_id,
        size_bytes=getattr(media, "file_size", None),
        message_id=message.message_id,
    )
