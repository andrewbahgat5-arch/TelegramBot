"""Unit tests for the download handlers (MASTER_PLAN Task 5.9)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.download import (
    handle_format_choice,
    handle_quality_choice,
    handle_url,
)
from domain.entities.media import MediaFormatOption, MediaInfo
from domain.enums import MediaFormat, Quality
from domain.exceptions import ExtractionFailedError, URLNotSupportedError
from services.url_analyzer import URLAnalyzerService
from tests.unit._fakes import FakeMediaRepo, FakeProvider, make_cache_service

_URL = "https://example.org/clip"


def _result() -> MediaInfo:
    return MediaInfo(
        platform="x",
        video_id="vid",
        title="A Clip",
        source_url=_URL,
        formats=(
            MediaFormatOption(MediaFormat.VIDEO, Quality.P720, 1_000_000, "a"),
            MediaFormatOption(MediaFormat.AUDIO, Quality.AUDIO, 100_000, "b"),
        ),
    )


def _analyzer(error: Exception | None = None) -> URLAnalyzerService:
    downloader = FakeProvider("ytdlp", result=_result(), error=error)
    cache_service, _ = make_cache_service()
    return URLAnalyzerService(downloader, cache_service, FakeMediaRepo())


def _session() -> AsyncSession:
    return object()  # type: ignore[return-value]  # analyzer factory ignores it here


async def test_url_message_shows_format_keyboard() -> None:
    analyzer = _analyzer()
    message = AsyncMock(spec=Message)
    message.text = _URL
    message.answer = AsyncMock()

    await handle_url(message, _session(), lambda s: analyzer, CallbackSigner("k"))

    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is not None


async def test_url_message_unsupported_replies_without_keyboard() -> None:
    analyzer = _analyzer(error=URLNotSupportedError())
    message = AsyncMock(spec=Message)
    message.text = _URL
    message.answer = AsyncMock()

    await handle_url(message, _session(), lambda s: analyzer, CallbackSigner("k"))

    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is None


async def test_url_message_extraction_failed_replies() -> None:
    analyzer = _analyzer(error=ExtractionFailedError())
    message = AsyncMock(spec=Message)
    message.text = _URL
    message.answer = AsyncMock()
    await handle_url(message, _session(), lambda s: analyzer, CallbackSigner("k"))
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is None


async def test_url_message_no_formats_replies() -> None:
    downloader = FakeProvider(
        "ytdlp",
        result=MediaInfo(platform="x", video_id="v", title="T", source_url=_URL, formats=()),
    )
    cache_service, _ = make_cache_service()
    analyzer = URLAnalyzerService(downloader, cache_service, FakeMediaRepo())
    message = AsyncMock(spec=Message)
    message.text = _URL
    message.answer = AsyncMock()
    await handle_url(message, _session(), lambda s: analyzer, CallbackSigner("k"))
    args = message.answer.await_args
    assert args is not None and args.kwargs.get("reply_markup") is None


async def test_format_choice_expired_media_alerts() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()  # repo is empty → analyze_by_media_id returns None
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_format(123, MediaFormat.VIDEO)
    callback.answer = AsyncMock()
    await handle_format_choice(callback, _session(), lambda s: analyzer, signer)
    callback.answer.assert_awaited_once()
    args = callback.answer.await_args
    assert args is not None and args.kwargs.get("show_alert") is True


async def test_format_choice_shows_quality_keyboard() -> None:
    signer = CallbackSigner("k")
    analyzer = _analyzer()
    analyzed = await analyzer.analyze(_URL)  # populate repo + cache

    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_format(analyzed.media_id, MediaFormat.VIDEO)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_format_choice(callback, _session(), lambda s: analyzer, signer)

    callback.message.edit_text.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_format_choice_forged_data_ignored() -> None:
    analyzer = _analyzer()
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "f|1|video|deadbeef00"  # bad signature
    callback.answer = AsyncMock()

    called = False

    def factory(s: AsyncSession) -> URLAnalyzerService:
        nonlocal called
        called = True
        return analyzer

    await handle_format_choice(callback, _session(), factory, CallbackSigner("k"))

    callback.answer.assert_awaited_once()
    assert called is False  # forged callback never reaches the analyzer


async def test_quality_choice_confirms_selection() -> None:
    signer = CallbackSigner("k")
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = signer.pack_quality(3, MediaFormat.VIDEO, Quality.P720)
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    await handle_quality_choice(callback, signer)

    callback.answer.assert_awaited_once()
    callback.message.edit_text.assert_awaited_once()


async def test_quality_choice_forged_ignored() -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = "q|x|video|720p|bad"
    callback.answer = AsyncMock()

    await handle_quality_choice(callback, CallbackSigner("k"))
    callback.answer.assert_awaited_once()
