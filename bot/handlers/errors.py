"""Global last-resort error handler.

Any exception that escapes a handler ends up here instead of aiogram's default
"unhandled exception" dump: it is logged as a structured ``update_handling_failed``
event (with the traceback and enough update context to reproduce), and the user gets
a localized "something went wrong on our side" reply so the bot never appears to
silently ignore a tap or a message.

This is a backstop, not a substitute for per-handler error handling — handlers that
can fail in *expected* ways (analysis, downloads, rate limits) keep their own precise
messages; only genuine bugs and unforeseen infrastructure failures land here.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import ErrorEvent

from core.error_report import RequestContext, Severity, UserContext
from core.i18n import translate
from core.logging import get_correlation_id, get_logger
from services.error_report_service import ErrorReportService

router = Router(name="errors")
_log = get_logger("bot.handlers.errors")


def _guess_locale(language_code: str | None) -> str:
    """Best-effort locale for the apology reply. Middleware-resolved ``data["locale"]``
    is not available on the errors observer (auth/i18n attach to the message and
    callback observers), so fall back to Telegram's client language."""
    return "ar" if (language_code or "").lower().startswith("ar") else "en"


@router.errors()
async def handle_update_error(
    event: ErrorEvent, error_report_service: ErrorReportService | None = None
) -> None:
    update = event.update
    message = update.message
    callback = update.callback_query
    from_user = (
        (message.from_user if message else None)
        or (callback.from_user if callback else None)
    )
    _log.error(
        "update_handling_failed",
        update_id=update.update_id,
        update_kind="callback_query" if callback else "message" if message else "other",
        user_id=from_user.id if from_user else None,
        exc_info=event.exception,
    )
    # An exception reaching the backstop is by definition unforeseen, so it is
    # CRITICAL and bypasses the alert throttle: the Owner gets the full trace, the
    # user who hit it, and the chat, without opening the server.
    if error_report_service is not None:
        chat = message or (callback.message if callback else None)
        await error_report_service.report_exception(
            event.exception,
            severity=Severity.CRITICAL,
            kind="unhandled_exception",
            user=UserContext(
                telegram_id=from_user.id if from_user else None,
                username=from_user.username if from_user else None,
                first_name=from_user.first_name if from_user else None,
                last_name=from_user.last_name if from_user else None,
                language=from_user.language_code if from_user else None,
                is_premium=getattr(from_user, "is_premium", None) if from_user else None,
                chat_id=getattr(chat, "id", None),
                chat_type=getattr(getattr(chat, "chat", chat), "type", None),
                action="callback_query" if callback else "message",
            ),
            request=RequestContext(
                url=(message.text if message and message.text else None),
                stage="update_handling",
            ),
            correlation_id=get_correlation_id(),
        )

    # Best-effort user notification — never let the apology itself raise.
    locale = _guess_locale(from_user.language_code if from_user else None)
    try:
        if callback is not None:
            await callback.answer(translate("errors.unexpected", locale), show_alert=True)
        elif message is not None:
            await message.answer(translate("errors.unexpected", locale))
    except Exception:  # noqa: S110 - chat may be gone/blocked; the log entry stands
        pass
