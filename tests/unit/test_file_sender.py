"""Unit tests for TelegramFileSender send-method routing (Sprint 6 follow-up).

Regression cover for the ogg/opus voice-note bug and the duplicate-delivery fix:
audio containers route to the right Telegram method, and ``file_id`` is extracted
from whichever media field the send produced (including voice).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from domain.enums import MediaFormat, Quality
from domain.exceptions import CachedFileExpiredError, TelegramUploadError
from infrastructure.telegram.file_sender import TelegramFileSender, _extract_upload


def _msg(**media: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "video": None,
        "audio": None,
        "document": None,
        "voice": None,
        "message_id": 4242,
    }
    fields.update(media)
    return SimpleNamespace(**fields)


def _ref(file_id: str) -> SimpleNamespace:
    return SimpleNamespace(file_id=file_id, file_unique_id=f"u-{file_id}", file_size=10)


def _bot_returning(message: SimpleNamespace) -> AsyncMock:
    bot = AsyncMock()
    bot.send_video = AsyncMock(return_value=message)
    bot.send_audio = AsyncMock(return_value=message)
    bot.send_document = AsyncMock(return_value=message)
    return bot


async def test_video_uses_send_video(tmp_path: Path) -> None:
    bot = _bot_returning(_msg(video=_ref("vfid")))
    sender = TelegramFileSender(bot)
    result = await sender.upload(
        tmp_path, format_=MediaFormat.VIDEO, quality=Quality.P720, chat_id=1, filename="v.mp4"
    )
    bot.send_video.assert_awaited_once()
    assert result.file_id == "vfid"


async def test_mp3_uses_send_audio(tmp_path: Path) -> None:
    bot = _bot_returning(_msg(audio=_ref("afid")))
    sender = TelegramFileSender(bot)
    await sender.upload(
        tmp_path, format_=MediaFormat.AUDIO, quality=Quality.MP3, chat_id=1, filename="a.mp3"
    )
    bot.send_audio.assert_awaited_once()
    bot.send_document.assert_not_awaited()


@pytest.mark.parametrize("quality", [Quality.OGG, Quality.OPUS, Quality.FLAC])
async def test_voice_prone_audio_uses_send_document(tmp_path: Path, quality: Quality) -> None:
    # ogg/opus would become a voice note via send_audio; flac is not rendered as music.
    bot = _bot_returning(_msg(document=_ref("dfid")))
    sender = TelegramFileSender(bot)
    await sender.upload(
        tmp_path,
        format_=MediaFormat.AUDIO,
        quality=quality,
        chat_id=1,
        filename=f"a.{quality.value}",
    )
    bot.send_document.assert_awaited_once()
    bot.send_audio.assert_not_awaited()


async def test_send_cached_matches_upload_method(tmp_path: Path) -> None:
    bot = _bot_returning(_msg(document=_ref("dfid")))
    sender = TelegramFileSender(bot)
    await sender.send_cached(99, "dfid", format_=MediaFormat.AUDIO, quality=Quality.OPUS)
    bot.send_document.assert_awaited_once()


def test_extract_upload_handles_voice() -> None:
    # Defensive: if Telegram returns a voice message, still capture the file_id.
    uploaded = _extract_upload(_msg(voice=_ref("vc")))  # type: ignore[arg-type]
    assert uploaded.file_id == "vc"


def _bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=SimpleNamespace(), message=message)  # type: ignore[arg-type]


async def test_send_cached_invalid_file_id_raises_cache_expired() -> None:
    # A file_id from another bot/API server → self-healing signal, not a hard error.
    bot = AsyncMock()
    bot.send_audio = AsyncMock(side_effect=_bad_request("wrong file identifier/HTTP URL specified"))
    sender = TelegramFileSender(bot)
    with pytest.raises(CachedFileExpiredError):
        await sender.send_cached(1, "stale", format_=MediaFormat.AUDIO, quality=Quality.MP3)


async def test_send_cached_other_bad_request_is_upload_error() -> None:
    bot = AsyncMock()
    bot.send_audio = AsyncMock(side_effect=_bad_request("chat not found"))
    sender = TelegramFileSender(bot)
    with pytest.raises(TelegramUploadError):
        await sender.send_cached(1, "fid", format_=MediaFormat.AUDIO, quality=Quality.MP3)
