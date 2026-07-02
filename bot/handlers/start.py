"""/start handler (MASTER_PLAN Task 4.8 + Sprint 9.5 home placement + Sprint 11.5 i18n).

Greets the already-resolved user in their current locale (defaults to
``DEFAULT_LOCALE`` on first contact — no forced first-run picker, Sprint 11.5),
offers a permanent "Change Language" entry point, then runs the best-effort
``home`` ad placement (no-op unless the Owner has enabled
``ad_placement_home_enabled``). No business logic beyond delegating to
``AdService``/``UserService`` (Section 9.1).

Also owns the shared "apply a language pick" flow (:func:`apply_language_pick`),
reused by the admin panel's own "Language" section — one persistence + confirmation
path regardless of entry point.
"""

from __future__ import annotations

from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import show_placement_ad
from bot.keyboards.language_select import build_change_language_button, build_language_picker
from core.i18n import Translator, list_enabled_locales
from domain.entities.user import UserSnapshot
from domain.enums import AdPlacement
from services.ad_service import AdService
from services.user_service import UserService

router = Router(name="start")

UserServiceFactory = Callable[[AsyncSession], UserService]


@router.message(CommandStart())
async def handle_start(
    message: Message,
    translate: Translator,
    locale: str,
    callback_signer: CallbackSigner,
    user: UserSnapshot | None = None,
    session: AsyncSession | None = None,
    ad_service_factory: Callable[[AsyncSession], AdService] | None = None,
) -> None:
    name = user.first_name if user and user.first_name else None
    text = (
        translate("start.welcome_named", locale, name=name)
        if name
        else translate("start.welcome_anonymous", locale)
    )
    await message.answer(text, reply_markup=build_change_language_button(callback_signer, locale))
    if user is not None and session is not None and ad_service_factory is not None:
        await show_placement_ad(ad_service_factory(session), user, AdPlacement.HOME.value)


@router.callback_query(F.data.startswith("l|"))
async def handle_language_callback(
    callback: CallbackQuery,
    translate: Translator,
    locale: str,
    callback_signer: CallbackSigner,
    user_service_factory: UserServiceFactory,
    session: AsyncSession,
    user: UserSnapshot,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "l" or parsed.language is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return

    if not parsed.language:  # open-picker sentinel
        await callback.answer()
        await _edit_text(
            callback,
            translate("language.picker_prompt", locale),
            build_language_picker(callback_signer),
        )
        return

    await apply_language_pick(
        callback,
        code=parsed.language,
        translate=translate,
        user_service_factory=user_service_factory,
        session=session,
        user=user,
    )


async def apply_language_pick(
    callback: CallbackQuery,
    *,
    code: str,
    translate: Translator,
    user_service_factory: UserServiceFactory,
    session: AsyncSession,
    user: UserSnapshot,
) -> None:
    """Validate + persist a language pick, then confirm **in the newly chosen
    locale** — not the request's already-resolved ``data["locale"]``, which
    reflects the value from *before* this update ran. Shared by the regular
    ``/start`` entry point and the admin panel's "Language" section.
    """
    enabled = {meta.code: meta.native_name for meta in list_enabled_locales()}
    if code not in enabled:
        await callback.answer()  # stale/disabled option tapped — ignore silently
        return

    await user_service_factory(session).set_language(user.telegram_id, code)
    await callback.answer()
    await _edit_text(callback, translate("language.updated", code, native_name=enabled[code]))


async def _edit_text(
    callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard)
