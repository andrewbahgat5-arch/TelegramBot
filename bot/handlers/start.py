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
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner
from bot.handlers.ads import show_placement_ad
from bot.keyboards.language_select import (
    OPEN_PICKER_SENTINEL,
    build_language_picker,
)
from bot.keyboards.user_settings import build_user_settings
from core.i18n import Translator, list_enabled_locales
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import AdPlacement
from services.ad_service import AdService
from services.queue_service import QueueService
from services.referral_service import ReferralService
from services.settings_service import SettingsService
from services.user_preference_service import UserPreferenceService
from services.user_service import UserService

router = Router(name="start")
_log = get_logger("bot.handlers.start")

UserServiceFactory = Callable[[AsyncSession], UserService]
ReferralServiceFactory = Callable[[AsyncSession], ReferralService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
UserPreferenceServiceFactory = Callable[[AsyncSession], UserPreferenceService]


def render_home(
    user: UserSnapshot | None, signer: CallbackSigner, translate: Translator, locale: str
) -> tuple[str, InlineKeyboardMarkup]:
    """The /start home view: welcome text + a menu. Reused by handle_start (new message),
    the Settings Back button, and the post-language-change reopen (all edit in place)."""
    name = user.first_name if user and user.first_name else None
    text = (
        translate("start.welcome_named", locale, name=name)
        if name
        else translate("start.welcome_anonymous", locale)
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=translate("settings.open_button", locale),
                    callback_data=signer.pack_user_setting(-1),
                )
            ],
            [
                InlineKeyboardButton(
                    text=translate("language.change_button", locale),
                    callback_data=signer.pack_language(OPEN_PICKER_SENTINEL, "s"),
                )
            ],
        ]
    )
    return text, keyboard


def _user_settings_text(translate: Translator, locale: str) -> str:
    return "\n".join(
        [
            translate("settings.header", locale),
            "",
            translate("settings.intro_auto", locale),
            "",
            translate("settings.intro_caption", locale),
            "",
            translate("settings.legend", locale),
        ]
    )
_REFERRAL_PREFIX = "ref_"


@router.message(CommandStart())
async def handle_start(
    message: Message,
    command: CommandObject,
    translate: Translator,
    locale: str,
    callback_signer: CallbackSigner,
    user: UserSnapshot | None = None,
    session: AsyncSession | None = None,
    ad_service_factory: Callable[[AsyncSession], AdService] | None = None,
    referral_service_factory: ReferralServiceFactory | None = None,
) -> None:
    text, keyboard = render_home(user, callback_signer, translate, locale)
    await message.answer(text, reply_markup=keyboard)
    if (
        command.args
        and command.args.startswith(_REFERRAL_PREFIX)
        and user is not None
        and session is not None
        and referral_service_factory is not None
    ):
        await _process_referral_deeplink(
            message,
            code=command.args[len(_REFERRAL_PREFIX) :],
            new_user_id=user.id,
            referral=referral_service_factory(session),
            translate=translate,
            locale=locale,
        )
    if user is not None and session is not None and ad_service_factory is not None:
        await show_placement_ad(ad_service_factory(session), user, AdPlacement.HOME.value)


async def _process_referral_deeplink(
    message: Message,
    *,
    code: str,
    new_user_id: int,
    referral: ReferralService,
    translate: Translator,
    locale: str,
) -> None:
    """Apply a ``?start=ref_CODE`` referral and best-effort notify the referrer (13.7)."""
    result = await referral.process_referral(code, new_user_id)
    if not result.success or result.referrer_telegram_id is None or message.bot is None:
        return
    try:
        await message.bot.send_message(
            result.referrer_telegram_id,
            translate(
                "referral.notify",
                locale,
                reward=result.reward_downloads,
                total=result.referrer_total_referrals,
            ),
        )
    except TelegramAPIError as exc:  # referrer blocked the bot / deleted account
        _log.info("referral_notify_failed", referrer=result.referrer_telegram_id, error=str(exc))


@router.message(Command("referral"))
async def handle_referral(
    message: Message,
    translate: Translator,
    locale: str,
    user: UserSnapshot | None = None,
    session: AsyncSession | None = None,
    referral_service_factory: ReferralServiceFactory | None = None,
    settings_service_factory: SettingsServiceFactory | None = None,
) -> None:
    """Show the caller their personal referral link, invite count, and bonus (13.7)."""
    if user is None or session is None or referral_service_factory is None:
        return
    reward = 0
    if settings_service_factory is not None:
        settings = settings_service_factory(session)
        if not bool(await settings.get("referral_enabled")):
            await message.answer(translate("referral.disabled", locale))
            return
        reward = int(await settings.get("referral_reward_downloads"))
    stats = await referral_service_factory(session).get_user_referral_stats(user.id)
    await message.answer(
        translate(
            "referral.screen",
            locale,
            link=stats.referral_link,
            reward=reward,
            invited=stats.total_invited,
            bonus=stats.total_bonus_downloads,
        )
    )


@router.callback_query(F.data.startswith("l|"))
async def handle_language_callback(
    callback: CallbackQuery,
    translate: Translator,
    locale: str,
    callback_signer: CallbackSigner,
    user_service_factory: UserServiceFactory,
    session: AsyncSession,
    user: UserSnapshot,
    queue_service: QueueService | None = None,
) -> None:
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "l" or parsed.language is None:
        await callback.answer()  # forged/garbled → ignore silently (Section 14.2)
        return

    origin = parsed.origin or "s"  # default to Start for legacy 3-part callbacks (#7)
    if not parsed.language:  # open-picker sentinel
        await callback.answer()
        await _edit_text(
            callback,
            translate("language.picker_prompt", locale),
            build_language_picker(callback_signer, origin),
        )
        return

    await apply_language_pick(
        callback,
        code=parsed.language,
        translate=translate,
        user_service_factory=user_service_factory,
        session=session,
        user=user,
        signer=callback_signer,
        origin=origin,
        queue_service=queue_service,
    )


async def apply_language_pick(
    callback: CallbackQuery,
    *,
    code: str,
    translate: Translator,
    user_service_factory: UserServiceFactory,
    session: AsyncSession,
    user: UserSnapshot,
    signer: CallbackSigner,
    origin: str = "s",
    queue_service: QueueService | None = None,
) -> None:
    """Validate + persist a language pick, then **reopen the screen it was launched from**
    in the newly chosen locale (item #7) — Start (``origin="s"``) or the admin panel home
    (``origin="p"``) — instead of a dead-end confirmation. All text is rendered in ``code``
    (the new locale), never the request's already-resolved ``data["locale"]`` (pre-update).
    """
    enabled = {meta.code: meta.native_name for meta in list_enabled_locales()}
    if code not in enabled:
        await callback.answer()  # stale/disabled option tapped — ignore silently
        return

    await user_service_factory(session).set_language(user.telegram_id, code)
    await callback.answer(translate("language.updated", code, native_name=enabled[code]))

    if origin == "p" and queue_service is not None:
        from bot.handlers.admin_panel import main_menu_view  # lazy: avoid import cycle

        text, markup = await main_menu_view(
            user_service_factory(session), queue_service, user.role, signer, translate, code
        )
        await _edit_text(callback, text, markup)
        return

    text, markup = render_home(user, signer, translate, code)
    await _edit_text(callback, text, markup)


@router.callback_query(F.data.startswith("us|"))
async def handle_user_settings(
    callback: CallbackQuery,
    translate: Translator,
    locale: str,
    callback_signer: CallbackSigner,
    session: AsyncSession,
    user: UserSnapshot,
    preference_service_factory: UserPreferenceServiceFactory | None = None,
) -> None:
    """User Settings screen (item #10): open (-1), back to Start (-2), or toggle (>=0)."""
    parsed = callback_signer.unpack(callback.data or "")
    if parsed is None or parsed.action != "us" or parsed.arg is None:
        await callback.answer()  # forged/garbled → ignore silently
        return
    if parsed.arg == -2:  # back to Start
        await callback.answer()
        text, markup = render_home(user, callback_signer, translate, locale)
        await _edit_text(callback, text, markup)
        return
    if preference_service_factory is None:
        await callback.answer()
        return
    prefs_service = preference_service_factory(session)
    if parsed.arg >= 0:  # flip a toggle, then re-render
        await prefs_service.toggle(user.id, parsed.arg)
    prefs = await prefs_service.get(user.id)
    await callback.answer()
    await _edit_text(
        callback,
        _user_settings_text(translate, locale),
        build_user_settings(prefs, callback_signer, locale),
    )


async def _edit_text(
    callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup | None = None
) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard)
