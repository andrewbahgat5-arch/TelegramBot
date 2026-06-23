"""Download handlers (MASTER_PLAN Task 5.9, flow 16.1 steps 1-4).

URL message → analyze → format keyboard → quality keyboard. The final quality pick
is acknowledged here; Sprint 6 (Task 6.8) hooks it to ``JobService.request`` to start
the actual download.

Per-request services are built from factories bound to the update's session,
injected as aiogram workflow data (``analyzer_factory``, ``callback_signer``).
"""

from __future__ import annotations

from collections.abc import Callable
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.keyboards.format_select import build_format_keyboard
from bot.keyboards.quality_select import build_quality_keyboard
from domain.exceptions import ExtractionFailedError, URLNotSupportedError
from services.url_analyzer import URLAnalyzerService

router = Router(name="download")

AnalyzerFactory = Callable[[AsyncSession], URLAnalyzerService]


@router.message(F.text.regexp(r"https?://"))
async def handle_url(
    message: Message,
    session: AsyncSession,
    analyzer_factory: AnalyzerFactory,
    callback_signer: CallbackSigner,
) -> None:
    analyzer = analyzer_factory(session)
    try:
        analyzed = await analyzer.analyze(message.text or "")
    except URLNotSupportedError:
        await message.answer("That link isn't supported. Please try a different one.")
        return
    except ExtractionFailedError:
        await message.answer("Sorry, I couldn't read that link. It may be private or removed.")
        return

    if not analyzed.info.formats:
        await message.answer("No downloadable formats were found for that link.")
        return

    keyboard = build_format_keyboard(analyzed.media_id, analyzed.info, callback_signer)
    await message.answer(
        f"<b>{escape(analyzed.info.title)}</b>\nChoose a format:", reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("f|"))
async def handle_format_choice(
    callback: CallbackQuery,
    session: AsyncSession,
    analyzer_factory: AnalyzerFactory,
    callback_signer: CallbackSigner,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "f":
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return

    analyzed = await analyzer_factory(session).analyze_by_media_id(parsed.media_id)
    if analyzed is None:
        await callback.answer("This link expired — please send it again.", show_alert=True)
        return

    keyboard = build_quality_keyboard(
        parsed.media_id, parsed.format, analyzed.info, callback_signer
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Choose a quality:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("q|"))
async def handle_quality_choice(callback: CallbackQuery, callback_signer: CallbackSigner) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "q" or parsed.quality is None:
        await callback.answer()
        return

    # Sprint 6 (Task 6.8) hooks JobService.request here to enqueue the download.
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Selected {parsed.format.value} · {parsed.quality.value}. "
            "Downloading will be available soon."
        )
