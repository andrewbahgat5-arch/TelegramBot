"""Admin inline control panel handlers (Sprint 9.6, F-2 / EP-22; Sprint 11.5 i18n).

``/admin`` opens the root panel; ``/settings`` opens the Settings panel directly.
Both are ``StaffFilter`` (owner + moderator); a non-staff user matches no handler
and is silently ignored (item #18). Almost all administration then happens through
the inline keyboards — navigation and read views land here; write actions (settings
edits, user / ad management, broadcast, wizards) arrive in later 9.6 tasks.

No business logic (Section 9.1): :class:`PanelFilter` verifies + parses the signed
callback and injects ``panel``; handlers delegate to the existing services and
render, editing the panel's own message in place to keep the chat clean.

Authorization is layered (defense in depth on top of hiding write buttons from
moderators in the keyboard layer):

* read navigation — ``PanelFilter(mutating=False)`` + ``StaffFilter``;
* write actions — ``PanelFilter(mutating=True)`` + ``OwnerFilter``;
* a final ``P|`` fallback silently acks forged or unauthorized callbacks (no spinner,
  no leak).

Every screen renders in the viewer's own ``locale`` (Sprint 11.5) — the panel is
staff-facing UI, no less localized than the regular-user surface. Only genuinely
dynamic content (usernames, ad titles/bodies, error messages, raw counts/ids) is
interpolated verbatim; everything else is a ``core.i18n`` key.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.filters.panel_filter import PanelFilter
from bot.filters.role_filter import RoleFilter, StaffFilter
from bot.handlers import admin_wizard
from bot.keyboards.admin_panel import (
    build_ad_action_list,
    build_ad_detail,
    build_ad_list,
    build_confirm,
    build_input_prompt,
    build_main_menu,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    build_user_detail,
    build_user_list,
)
from bot.keyboards.language_select import build_language_picker
from bot.panel import ui
from bot.panel.registry import SECTIONS, SETTING_FIELDS, SettingField, setting_field
from bot.panel.states import PanelStates
from core.i18n import Translator, list_enabled_locales
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.ad_service import AdService
from services.admin_service import AdminService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService, InvalidBroadcastError
from services.queue_service import QueueService
from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
)
from services.user_service import UserService

router = Router(name="admin_panel")
_log = get_logger("bot.handlers.admin_panel")

UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
AdminServiceFactory = Callable[[AsyncSession], AdminService]
AdServiceFactory = Callable[[AsyncSession], AdService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]
AudienceServiceFactory = Callable[[AsyncSession], AudienceService]

OwnerFilter = RoleFilter(UserRole.OWNER)

_OWNER_ONLY_SECTIONS = frozenset(section.code for section in SECTIONS if section.owner_only)
_LIST_LIMIT = 20


# --- entry commands -------------------------------------------------------
@router.message(Command("admin"), StaffFilter)
async def open_panel(
    message: Message,
    user: UserSnapshot,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    await message.answer(
        translate("panel.main_title", locale),
        reply_markup=build_main_menu(user.role, callback_signer, locale),
    )


@router.message(Command("settings"), StaffFilter)
async def open_settings(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    text = await _settings_text(settings_service_factory(session), translate, locale)
    await message.answer(text, reply_markup=build_settings_menu(user.role, callback_signer, locale))


# --- read navigation ------------------------------------------------------
@router.callback_query(PanelFilter(mutating=False), StaffFilter)
async def panel_navigate(
    callback: CallbackQuery,
    panel: ParsedPanel,
    session: AsyncSession,
    user: UserSnapshot,
    state: FSMContext,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    ad_service_factory: AdServiceFactory,
    admin_service_factory: AdminServiceFactory,
    queue_service: QueueService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    await state.clear()  # navigating away cancels any pending guided input
    # "User Info" with no target → start the guided id-lookup wizard (9.6.8).
    if panel.section == "u" and panel.action == "inf" and panel.arg is None:
        await _arm_user_lookup(callback, state, callback_signer, translate, locale)
        return
    # Owner-only sections are hidden from moderators; guard the callback too.
    if panel.section in _OWNER_ONLY_SECTIONS and user.role is not UserRole.OWNER:
        await callback.answer()
        return
    rendered = await _render(
        panel,
        user,
        session,
        callback_signer,
        user_service_factory,
        settings_service_factory,
        ad_service_factory,
        admin_service_factory,
        queue_service,
        translate,
        locale,
    )
    if rendered is not None and isinstance(callback.message, Message):
        text, markup = rendered
        await _safe_edit(callback.message, text, markup)
    await callback.answer()


# --- write actions --------------------------------------------------------
@router.callback_query(PanelFilter(mutating=True), OwnerFilter)
async def panel_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    session: AsyncSession,
    user: UserSnapshot,
    state: FSMContext,
    user_service_factory: UserServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    admin_service_factory: AdminServiceFactory,
    ad_service_factory: AdServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    audience_service_factory: AudienceServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    if panel.section == "w":  # compose wizard — manages its own FSM state (no clear)
        await admin_wizard.dispatch(
            callback,
            panel,
            state,
            session=session,
            user=user,
            signer=callback_signer,
            ad_service_factory=ad_service_factory,
            broadcast_service_factory=broadcast_service_factory,
            audience_service_factory=audience_service_factory,
            translate=translate,
            locale=locale,
        )
        return
    await state.clear()  # a fresh write cancels any stale guided input ("ev" re-arms below)
    # Compose-wizard entry points (9.6.10): Ads "Create" / Broadcast "Create" + presets.
    if panel.section == "a" and panel.action == "cr":
        await admin_wizard.start(callback, state, callback_signer, translate, locale, kind="ad")
        return
    if panel.section == "a" and panel.action == "ed" and panel.arg is not None:
        # Full edit-in-wizard: load the existing ad into the compose wizard (Bug-fix sprint).
        await admin_wizard.start_edit(
            callback,
            panel.arg,
            state,
            callback_signer,
            translate,
            locale,
            ads=ad_service_factory(session),
            audience=audience_service_factory(session),
        )
        return
    if panel.section == "b" and panel.action in ("cr", "bf", "bp", "ba", "bl"):
        await admin_wizard.start(
            callback, state, callback_signer, translate, locale, kind="broadcast"
        )
        return
    if panel.section == "s":  # Settings stepper / guided entry (9.6.5, 9.6.7)
        await _settings_write(
            callback,
            panel,
            settings_service_factory(session),
            user,
            callback_signer,
            state,
            translate,
            locale,
        )
        return
    if panel.section in ("u", "m"):  # Users + Moderation management (9.6.6, Owner req #10)
        await _users_write(
            callback,
            panel,
            user_service_factory(session),
            admin_service_factory(session),
            settings_service_factory(session),
            user,
            callback_signer,
            state,
            translate,
            locale,
        )
        return
    if panel.section == "a":  # Advertisements management (9.6.9)
        await _ads_write(
            callback,
            panel,
            ad_service_factory(session),
            broadcast_service_factory(session),
            user,
            callback_signer,
            translate,
            locale,
        )
        return
    # create/edit wizards land in 9.6.10.
    await callback.answer(translate("panel.action_unavailable", locale), show_alert=False)


async def _settings_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    settings: SettingsService,
    user: UserSnapshot,
    signer: CallbackSigner,
    state: FSMContext,
    translate: Translator,
    locale: str,
) -> None:
    """Open / step / type / save a numeric setting (LOCKED §13.4 keys only)."""
    field = setting_field(panel.arg) if panel.arg is not None else None
    if field is None:
        await callback.answer()
        return
    if panel.action == "ev":  # "✏️ Enter Value" → arm the guided-input wizard
        if isinstance(callback.message, Message):
            await state.set_state(PanelStates.setting_value)
            await state.update_data(
                field_index=field.index,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
            await _safe_edit(
                callback.message,
                _enter_value_text(field, translate, locale),
                build_input_prompt(
                    signer, locale, back=("s", "e", field.index), cancel=("s", "op", None)
                ),
            )
        await callback.answer()
        return
    if panel.action == "sv":  # persist the candidate value
        value = _clamp(field, panel.value if panel.value is not None else field.min_value)
        try:
            await settings.set_validated(field.key, str(value), updated_by=user.id)
        except (SettingNotFoundError, InvalidSettingValueError) as exc:
            await callback.answer(
                translate("panel.settings.save_failed", locale, error=str(exc)), show_alert=True
            )
            return
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                await _settings_text(settings, translate, locale),
                build_settings_menu(user.role, signer, locale),
            )
        label = translate(field.label_key, locale)
        await callback.answer(translate("panel.settings.saved", locale, label=label, value=value))
        return
    # "e" opens the stepper at the live value; "-"/"+" carry the candidate already
    # clamped by the keyboard builder.
    if panel.action == "e":
        value = await _current_int(settings, field)
    else:  # "-" or "+"
        value = panel.value if panel.value is not None else await _current_int(settings, field)
    value = _clamp(field, value)
    if isinstance(callback.message, Message):
        await _safe_edit(
            callback.message,
            _stepper_text(field, value, translate, locale),
            build_setting_stepper(field, value, signer, locale),
        )
    await callback.answer()


def _clamp(field: SettingField, value: int) -> int:
    return max(field.min_value, min(field.max_value, value))


async def _current_int(settings: SettingsService, field: SettingField) -> int:
    view = await settings.get_view(field.key)
    if view is None:
        return field.min_value
    try:
        return int(view.value)
    except ValueError:
        return field.min_value


def _stepper_text(field: SettingField, value: int, translate: Translator, locale: str) -> str:
    return translate(
        "panel.settings.stepper_body",
        locale,
        label=translate(field.label_key, locale),
        value=value,
        min=field.min_value,
        max=field.max_value,
        step=field.step,
    )


def _enter_value_text(field: SettingField, translate: Translator, locale: str) -> str:
    return translate(
        "panel.settings.enter_value_body",
        locale,
        label=translate(field.label_key, locale),
        min=field.min_value,
        max=field.max_value,
    )


# Destructive user actions: open a confirm screen first. Maps the open action →
# (confirmed action, verb translation key for the prompt). Additive actions (ubn/up)
# act directly.
_USER_CONFIRM = {
    "ban": ("banc", "panel.verb.ban"),
    "rp": ("rpc", "panel.verb.remove_premium_from"),
    "mka": ("mkac", "panel.verb.make_admin"),
    "rma": ("rmac", "panel.verb.remove_admin_from"),
}

# Top-level Users / Moderation actions carry no target id. Tapping one arms a guided
# "send the Telegram ID" prompt; the typed id then re-enters the same apply/confirm path
# the per-user detail buttons use (Owner req #10 — direct user-id input for every action).
_USER_ACTION_PROMPT = {
    "ban": "panel.prompt.ban_user",
    "ubn": "panel.prompt.unban_user",
    "up": "panel.prompt.upgrade_premium",
    "rp": "panel.prompt.remove_premium",
    "mka": "panel.prompt.make_admin",
    "rma": "panel.prompt.remove_admin",
}


async def _users_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    users: UserService,
    admin: AdminService,
    settings: SettingsService,
    actor: UserSnapshot,
    signer: CallbackSigner,
    state: FSMContext,
    translate: Translator,
    locale: str,
) -> None:
    """Ban / Unban / Premium / Admin on a selected user, destructive steps behind a confirm."""
    tid, action = panel.arg, panel.action
    if tid is None:  # a top-level submenu button (Users or Moderation) without a target
        if action in _USER_ACTION_PROMPT:  # arm the guided id-entry, then act (Owner req #10)
            await _arm_user_action(
                callback, state, panel.section, action, signer, translate, locale
            )
            return
        await callback.answer(translate("panel.users.tap_list_first", locale), show_alert=False)
        return
    if action in _USER_CONFIRM:  # render the confirm screen
        snap = await users.find(tid)
        if snap is None:
            await callback.answer(translate("panel.users.not_found", locale), show_alert=True)
            return
        confirmed, verb_key = _USER_CONFIRM[action]
        prompt = translate("panel.confirm.body", locale, verb=translate(verb_key, locale), id=tid)
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                prompt,
                build_confirm(
                    signer, locale, confirm=("u", confirmed, tid, None), cancel=("u", "inf", tid)
                ),
            )
        await callback.answer()
        return
    result = await _apply_user_action(users, action, tid, translate, locale)
    if result is None:
        await callback.answer(translate("panel.users.not_found", locale), show_alert=True)
        return
    _, toast = result
    view = await _user_detail_view(
        users, admin, settings, tid, actor.role, signer, translate, locale
    )
    if view is not None and isinstance(callback.message, Message):
        text, markup = view
        await _safe_edit(callback.message, text, markup)
    await callback.answer(toast)


async def _apply_user_action(
    users: UserService, action: str, tid: int, translate: Translator, locale: str
) -> tuple[UserSnapshot, str] | None:
    """Perform a (possibly already-confirmed) user write. Returns (snapshot, toast) or None."""
    if action == "ubn":
        snap = await users.unban(tid)
        return (snap, translate("panel.users.toast.unbanned", locale)) if snap else None
    if action == "up":
        snap = await users.set_premium(tid, is_premium=True)
        return (snap, translate("panel.users.toast.premium_granted", locale)) if snap else None
    if action == "banc":
        snap = await users.ban(tid)
        return (snap, translate("panel.users.toast.banned", locale)) if snap else None
    if action == "rpc":
        snap = await users.set_premium(tid, is_premium=False)
        return (snap, translate("panel.users.toast.premium_removed", locale)) if snap else None
    if action == "mkac":
        snap = await users.set_role(tid, UserRole.MODERATOR)
        return (snap, translate("panel.users.toast.promoted_admin", locale)) if snap else None
    if action == "rmac":
        snap = await users.set_role(tid, UserRole.USER)
        return (snap, translate("panel.users.toast.admin_removed", locale)) if snap else None
    return None


async def _user_detail_view(
    users: UserService,
    admin: AdminService,
    settings: SettingsService,
    tid: int,
    role: UserRole,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Build the extended User Info screen, or None if no such user."""
    snap = await users.find(tid)
    if snap is None:
        return None
    history_count = await admin.count_user_downloads(snap.id)
    active_jobs = await admin.count_user_active_jobs(snap.id)
    daily_limit = await settings.get(
        "premium_daily_limit" if snap.is_premium else "free_daily_limit"
    )
    text = _user_detail_text(
        snap,
        history_count=history_count,
        active_jobs=active_jobs,
        daily_limit=daily_limit,
        translate=translate,
        locale=locale,
    )
    return text, build_user_detail(snap, role, signer, locale)


def _user_detail_text(
    snap: UserSnapshot,
    *,
    history_count: int,
    active_jobs: int,
    daily_limit: object,
    translate: Translator,
    locale: str,
) -> str:
    name = escape(snap.first_name) if snap.first_name else "—"
    username = f"@{escape(snap.username)}" if snap.username else "—"
    if snap.is_banned:
        status = translate("panel.users.detail.banned_status", locale) + (
            f" — {escape(snap.ban_reason)}" if snap.ban_reason else ""
        )
    else:
        status = translate("panel.users.detail.active_status", locale)
    premium = translate(
        "panel.users.detail.premium_yes" if snap.is_premium else "panel.users.detail.premium_no",
        locale,
    )
    if snap.is_premium and snap.premium_expires_at is not None:
        premium += translate(
            "panel.users.detail.premium_until", locale, date=f"{snap.premium_expires_at:%Y-%m-%d}"
        )
    active_job = translate(
        "panel.users.detail.active_job_yes"
        if active_jobs > 0
        else "panel.users.detail.active_job_none",
        locale,
    )
    return translate(
        "panel.users.detail.body",
        locale,
        name=name,
        id=snap.telegram_id,
        username=username,
        language=snap.language or "—",
        role=snap.role.value,
        status=status,
        premium=premium,
        joined=_fmt_dt(snap.created_at),
        last_activity=_fmt_dt(snap.last_activity_at),
        total_downloads=snap.total_downloads,
        today=snap.daily_download_count,
        limit=daily_limit,
        history=history_count,
        active_job=active_job,
    )


def _fmt_dt(value: datetime.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else "—"


def _users_list_text(rows: list[UserSnapshot], translate: Translator, locale: str) -> str:
    if not rows:
        return translate("panel.users.list_empty", locale)
    return translate("panel.users.list_header", locale, count=len(rows))


def _user_lookup_text(translate: Translator, locale: str) -> str:
    return translate("panel.users.lookup_body", locale)


def _user_action_prompt_text(action: str, translate: Translator, locale: str) -> str:
    title_key = _USER_ACTION_PROMPT.get(action, "panel.prompt.manage_user_default")
    return translate("panel.users.action_prompt_body", locale, title=translate(title_key, locale))


async def _arm_user_action(
    callback: CallbackQuery,
    state: FSMContext,
    section: str,
    action: str,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Prompt for a Telegram id, then apply ``action`` to that user (Owner req #10)."""
    if isinstance(callback.message, Message):
        await state.set_state(PanelStates.user_action)
        await state.update_data(
            action=action,
            section=section,
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
        await _safe_edit(
            callback.message,
            _user_action_prompt_text(action, translate, locale),
            build_input_prompt(
                signer, locale, back=(section, "op", None), cancel=(section, "op", None)
            ),
        )
    await callback.answer()


async def _arm_user_lookup(
    callback: CallbackQuery,
    state: FSMContext,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Prompt for a Telegram id and arm the user_lookup wizard."""
    if isinstance(callback.message, Message):
        await state.set_state(PanelStates.user_lookup)
        await state.update_data(
            chat_id=callback.message.chat.id, message_id=callback.message.message_id
        )
        await _safe_edit(
            callback.message,
            _user_lookup_text(translate, locale),
            build_input_prompt(signer, locale, back=("u", "op", None), cancel=("u", "op", None)),
        )
    await callback.answer()


# --- forged / unauthorized fallback ---------------------------------------
@router.callback_query(F.data.startswith("P|"))
async def panel_ignore(callback: CallbackQuery) -> None:
    await callback.answer()  # silent: forged signature or a moderator's owner-only tap


# --- guided input: a typed setting value (9.6.7) --------------------------
@router.message(PanelStates.setting_value, OwnerFilter)
async def on_setting_value(
    message: Message,
    state: FSMContext,
    bot: Bot,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Capture the value the Owner typed for ✏️ Enter Value → confirm screen before saving."""
    data = await state.get_data()
    index, chat_id, message_id = (
        data.get("field_index"),
        data.get("chat_id"),
        data.get("message_id"),
    )
    field = setting_field(index) if isinstance(index, int) else None
    if field is None or chat_id is None or message_id is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        value = int(raw)
    except ValueError:
        await message.reply(translate("panel.settings.value_number_prompt", locale))
        return  # keep the state so the next message is still captured
    if not (field.min_value <= value <= field.max_value):
        await message.reply(
            translate(
                "panel.settings.value_range_error", locale, min=field.min_value, max=field.max_value
            )
        )
        return
    await state.clear()
    label = translate(field.label_key, locale)
    text = translate("panel.settings.confirm_set", locale, label=label, value=value)
    await bot.edit_message_text(
        text,
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=build_confirm(
            callback_signer,
            locale,
            confirm=("s", "sv", field.index, value),
            cancel=("s", "e", field.index),
        ),
    )


# --- guided input: a typed Telegram id for User Info (9.6.8) --------------
@router.message(PanelStates.user_lookup, StaffFilter)
async def on_user_lookup(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    admin_service_factory: AdminServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Capture the typed Telegram id and edit the panel to that user's extended detail."""
    data = await state.get_data()
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    if chat_id is None or message_id is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        tid = int(raw)
    except ValueError:
        await message.reply(translate("panel.users.numeric_id_prompt", locale))
        return  # keep the state for the next attempt
    await state.clear()
    view = await _user_detail_view(
        user_service_factory(session),
        admin_service_factory(session),
        settings_service_factory(session),
        tid,
        user.role,
        callback_signer,
        translate,
        locale,
    )
    if view is None:
        text: str = translate("panel.users.no_id_found", locale, id=tid)
        markup = build_section_menu("u", user.role, callback_signer, locale)
    else:
        text, markup = view
    await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


# --- guided input: a typed Telegram id for a Users / Moderation action (Owner #10) ---
@router.message(PanelStates.user_action, OwnerFilter)
async def on_user_action_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    admin_service_factory: AdminServiceFactory,
    settings_service_factory: SettingsServiceFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Apply a top-level Users / Moderation action to the typed Telegram id.

    Destructive actions (ban / remove premium / make-or-remove admin) route through the
    same confirm screen the detail buttons use; additive ones (unban / upgrade premium)
    act directly. The owner can never be targeted from the panel.
    """
    data = await state.get_data()
    action, section = data.get("action"), data.get("section")
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    if not isinstance(action, str) or chat_id is None or message_id is None:
        await state.clear()
        return
    menu_section = section if isinstance(section, str) else "u"
    raw = (message.text or "").strip()
    try:
        tid = int(raw)
    except ValueError:
        await message.reply(translate("panel.users.numeric_id_prompt", locale))
        return  # keep the state for the next attempt
    await state.clear()
    users = user_service_factory(session)
    snap = await users.find(tid)
    menu = build_section_menu(menu_section, user.role, callback_signer, locale)
    if snap is None:
        await bot.edit_message_text(
            translate("panel.users.no_id_found", locale, id=tid),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=menu,
        )
        return
    if snap.role is UserRole.OWNER:  # mirror build_user_detail: the owner is untouchable
        await bot.edit_message_text(
            translate("panel.users.owner_untouchable", locale),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=menu,
        )
        return
    if action in _USER_CONFIRM:  # destructive → confirm screen (same as the detail flow)
        confirmed, verb_key = _USER_CONFIRM[action]
        await bot.edit_message_text(
            translate("panel.confirm.body", locale, verb=translate(verb_key, locale), id=tid),
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=build_confirm(
                callback_signer,
                locale,
                confirm=("u", confirmed, tid, None),
                cancel=("u", "inf", tid),
            ),
        )
        return
    # additive (unban / upgrade premium) → apply directly, then show the detail screen
    await _apply_user_action(users, action, tid, translate, locale)
    view = await _user_detail_view(
        users,
        admin_service_factory(session),
        settings_service_factory(session),
        tid,
        user.role,
        callback_signer,
        translate,
        locale,
    )
    if view is not None:
        text, markup = view
        await bot.edit_message_text(
            text, chat_id=chat_id, message_id=message_id, reply_markup=markup
        )


# --- guided input: compose wizard typed value / content (9.6.10) ----------
@router.message(PanelStates.wizard_text, OwnerFilter)
async def on_wizard_text(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    callback_signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await admin_wizard.on_text(
        message, state, bot, session, callback_signer, ad_service_factory, translate, locale
    )


@router.message(PanelStates.wizard_content, OwnerFilter)
async def on_wizard_content(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    callback_signer: CallbackSigner,
    ad_service_factory: AdServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    await admin_wizard.on_content(
        message, state, bot, session, callback_signer, ad_service_factory, translate, locale
    )


# --- rendering ------------------------------------------------------------
async def _render(
    panel: ParsedPanel,
    user: UserSnapshot,
    session: AsyncSession,
    signer: CallbackSigner,
    user_factory: UserServiceFactory,
    settings_factory: SettingsServiceFactory,
    ad_factory: AdServiceFactory,
    admin_factory: AdminServiceFactory,
    queue: QueueService,
    translate: Translator,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Map a verified read callback to (message text, keyboard). None → just ack."""
    section, action = panel.section, panel.action
    role = user.role
    if section == "mn":
        return translate("panel.main_title", locale), build_main_menu(role, signer, locale)
    if section == "l":  # personal language preference (Sprint 11.5) — same picker as /start
        return translate("language.picker_prompt", locale), build_language_picker(signer)
    if section == "s":
        if action == "inf":
            return _settings_info_text(panel.arg, translate, locale), build_settings_menu(
                role, signer, locale
            )
        return await _settings_text(
            settings_factory(session), translate, locale
        ), build_settings_menu(role, signer, locale)
    if section == "t":
        return await _stats_text(
            user_factory(session), queue, translate, locale
        ), build_section_menu("t", role, signer, locale)
    if section == "u":
        users = user_factory(session)
        if action == "inf" and panel.arg is not None:
            view = await _user_detail_view(
                users,
                admin_factory(session),
                settings_factory(session),
                panel.arg,
                role,
                signer,
                translate,
                locale,
            )
            if view is not None:
                return view
            return translate("panel.users.no_id_found", locale, id=panel.arg), build_section_menu(
                "u", role, signer, locale
            )
        if action == "ls":
            rows = await users.list_users(limit=_LIST_LIMIT)
            return _users_list_text(rows, translate, locale), build_user_list(rows, signer, locale)
        return translate("panel.users.section_body", locale), build_section_menu(
            "u", role, signer, locale
        )
    if section == "a":
        ads = ad_factory(session)
        if action == "inf" and panel.arg is not None:
            view = await _ad_detail_view(ads, panel.arg, role, signer, translate, locale)
            if view is not None:
                return view
            return translate("panel.ads.no_id_found", locale, id=panel.arg), build_section_menu(
                "a", role, signer, locale
            )
        if action == "ls":
            ad_rows = await ads.list_ads()
            return _ads_list_text(ad_rows, translate, locale), build_ad_list(
                ad_rows, signer, locale
            )
        if action == "stt":
            return await _overall_stats_text(ads, translate, locale), build_section_menu(
                "a", role, signer, locale
            )
        return translate("panel.ads.section_body", locale), build_section_menu(
            "a", role, signer, locale
        )
    if section == "b":
        return translate("panel.broadcast.section_body", locale), build_section_menu(
            "b", role, signer, locale
        )
    if section == "m":
        return await _users_text(
            user_factory(session), banned_only=True, translate=translate, locale=locale
        ), build_section_menu("m", role, signer, locale)
    if section == "h":
        return await _jobs_text(admin_factory(session), translate=translate, locale=locale), (
            build_section_menu("h", role, signer, locale)
        )
    if section == "d":
        text = (
            await _jobs_text(
                admin_factory(session),
                status="processing",
                title_key="panel.jobs.active_title",
                translate=translate,
                locale=locale,
            )
            if action == "ls"
            else await _queue_text(queue, translate, locale)
        )
        return text, build_section_menu("d", role, signer, locale)
    if section == "y":
        text = (
            await _errors_text(admin_factory(session), translate, locale)
            if action == "ls"
            else await _system_text(
                user_factory(session), settings_factory(session), queue, translate, locale
            )
        )
        return text, build_section_menu("y", role, signer, locale)
    return None


async def _safe_edit(message: Message, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # "message is not modified" when re-opening the same screen — harmless


async def _stats_text(
    users: UserService, queue: QueueService, translate: Translator, locale: str
) -> str:
    """Dashboard-grade Statistics screen (Sprint 13.2/13.4) built from ui.py primitives."""
    stats = await users.get_stats()
    depth, active = await queue.depth(), await queue.active_count()

    def label(name: str) -> str:
        return translate(f"panel.stats.label.{name}", locale)

    lines = [
        ui.header(translate("panel.stats.title", locale), icon=ui.emoji("stats")),
        "",
        ui.metric(ui.emoji("members"), label("members"), stats.total_users),
        ui.metric(ui.emoji("premium"), label("premium"), stats.premium_users),
        ui.metric(ui.emoji("moderator"), label("staff"), stats.staff_users),
        ui.metric(ui.badge("banned"), label("banned"), stats.banned_users),
        ui.divider(),
        ui.metric(ui.emoji("new"), label("new_today"), stats.new_today),
        ui.metric(ui.emoji("fire"), label("active_24h"), stats.active_24h),
        ui.metric(ui.emoji("fire"), label("active_7d"), stats.active_7d),
        ui.metric(ui.emoji("fire"), label("active_30d"), stats.active_30d),
        ui.divider(),
        ui.metric(ui.emoji("sleep"), label("inactive_5d"), stats.inactive_5d),
        ui.metric(ui.emoji("sleep"), label("inactive_7d"), stats.inactive_7d),
        ui.metric(ui.emoji("sleep"), label("inactive_30d"), stats.inactive_30d),
        ui.divider(),
        ui.metric(ui.emoji("active"), label("this_hour"), stats.active_current_hour),
        ui.metric(ui.emoji("active"), label("prev_hour"), stats.active_previous_hour),
        ui.divider(),
        ui.metric(ui.emoji("deleted"), label("deleted"), stats.deleted_users),
        ui.metric(ui.emoji("blocked"), label("blocked"), stats.blocked_users),
        ui.metric(ui.emoji("download"), label("downloads"), stats.total_downloads),
        ui.metric(ui.emoji("queue"), label("queue"), f"{depth} / {active}"),
        "",
        ui.footer(),
    ]
    return "\n".join(lines)


async def _users_text(
    users: UserService, *, banned_only: bool, translate: Translator, locale: str
) -> str:
    rows = await users.list_users(limit=_LIST_LIMIT)
    if banned_only:
        rows = [row for row in rows if row.is_banned]
    title = translate(
        "panel.users.banned_list_title" if banned_only else "panel.users.list_title", locale
    )
    if not rows:
        empty = translate(
            "panel.users.none_banned" if banned_only else "panel.users.none_yet", locale
        )
        return f"{title}\n\n{empty}"
    return "\n".join([title, "", *(_user_row(row) for row in rows)])


def _user_row(snap: UserSnapshot) -> str:
    username = f"@{escape(snap.username)}" if snap.username else "—"
    marker = "🚫" if snap.is_banned else ("⭐" if snap.is_premium else "•")
    return f"{marker} <code>{snap.telegram_id}</code> · {username} · {snap.role.value}"


# Destructive / high-impact ad actions route through a confirm screen first.
_AD_CONFIRM = {
    "de": ("dec", "panel.verb.delete_ad"),
    "bc": ("bcc", "panel.verb.broadcast_all"),
}

# Top-level Manage-Campaigns actions that need an ad chosen first → render a picker.
_AD_PICKER_ACTIONS = frozenset({"en", "di", "de", "bc", "ed"})
_AD_PICKER_VERB = {
    "en": "panel.verb.enable",
    "di": "panel.verb.disable",
    "de": "panel.verb.delete",
    "bc": "panel.verb.broadcast",
    "ed": "panel.verb.edit",
}


def _ad_picker_text(action: str, rows: Sequence[Any], translate: Translator, locale: str) -> str:
    if not rows:
        return translate("panel.ads.picker_empty", locale)
    verb_key = _AD_PICKER_VERB.get(action, "panel.verb.manage")
    return translate("panel.ads.picker_header", locale, verb=translate(verb_key, locale))


async def _ads_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    ads: AdService,
    broadcasts: BroadcastService,
    actor: UserSnapshot,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Enable / Disable / Delete / Broadcast a selected ad; destructive steps confirm first."""
    ad_id, action = panel.arg, panel.action
    if ad_id is None:
        # A top-level Manage-Campaigns action (no ad chosen yet): show an ad picker whose
        # rows carry the same action + an ad id, so the next tap is fully targeted.
        if action in _AD_PICKER_ACTIONS:
            rows = await ads.list_ads()
            if isinstance(callback.message, Message):
                await _safe_edit(
                    callback.message,
                    _ad_picker_text(action, rows, translate, locale),
                    build_ad_action_list(rows, action, signer, locale),
                )
            await callback.answer()
            return
        await callback.answer(translate("panel.ads.tap_list_first", locale), show_alert=False)
        return
    if action in _AD_CONFIRM:  # render the confirm screen
        if await ads.get(ad_id) is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        confirmed, verb_key = _AD_CONFIRM[action]
        prompt = translate(
            "panel.confirm.body_ad", locale, verb=translate(verb_key, locale), id=ad_id
        )
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                prompt,
                build_confirm(
                    signer,
                    locale,
                    confirm=("a", confirmed, ad_id, None),
                    cancel=("a", "inf", ad_id),
                ),
            )
        await callback.answer()
        return
    if action == "dec":  # confirmed delete
        deleted = await ads.delete(ad_id)
        toast = (
            translate("panel.ads.deleted", locale, id=ad_id)
            if deleted
            else translate("panel.ads.not_found", locale)
        )
        rows = await ads.list_ads()
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                _ads_list_text(rows, translate, locale),
                build_ad_list(rows, signer, locale),
            )
        await callback.answer(toast)
        return
    if action == "bcc":  # confirmed broadcast to all
        try:
            broadcast = await broadcasts.create_from_ad(
                created_by_user_id=actor.id, advertisement_id=ad_id
            )
        except InvalidBroadcastError as exc:
            await callback.answer(
                translate("panel.ads.broadcast_failed", locale, error=str(exc)), show_alert=True
            )
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(
            translate("panel.ads.broadcast_queued", locale, count=broadcast.expected_total)
        )
        return
    if action in ("en", "di"):  # enable / disable directly
        ad = await ads.set_active(ad_id, action == "en")
        if ad is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(
            translate(
                "panel.ads.enabled_toast" if action == "en" else "panel.ads.disabled_toast", locale
            )
        )
        return
    await callback.answer()


async def _rerender_ad_detail(
    callback: CallbackQuery,
    ads: AdService,
    ad_id: int,
    role: UserRole,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    view = await _ad_detail_view(ads, ad_id, role, signer, translate, locale)
    if view is not None and isinstance(callback.message, Message):
        text, markup = view
        await _safe_edit(callback.message, text, markup)


async def _ad_detail_view(
    ads: AdService,
    ad_id: int,
    role: UserRole,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    ad = await ads.get(ad_id)
    if ad is None:
        return None
    return _ad_detail_text(ad, translate, locale), build_ad_detail(ad, role, signer, locale)


def _ad_detail_text(ad: Any, translate: Translator, locale: str) -> str:
    state = translate(
        "panel.ads.state_active" if ad.is_active else "panel.ads.state_disabled", locale
    )
    ctr = f"{ad.clicks / ad.impressions * 100:.1f}%" if ad.impressions else "—"
    return translate(
        "panel.ads.detail_body",
        locale,
        title=escape(ad.title),
        id=ad.id,
        type=ad.type,
        state=state,
        target=ad.target_role or translate("panel.ads.target_all", locale),
        priority=ad.priority,
        frequency=ad.show_every_n_downloads,
        impressions=ad.impressions,
        clicks=ad.clicks,
        ctr=ctr,
    )


def _ads_list_text(rows: Sequence[Any], translate: Translator, locale: str) -> str:
    if not rows:
        return translate("panel.ads.list_empty", locale)
    return translate("panel.ads.list_header", locale, count=len(rows))


async def _overall_stats_text(ads: AdService, translate: Translator, locale: str) -> str:
    stats = await ads.overall_stats()
    ctr = f"{stats.clicks / stats.impressions * 100:.1f}%" if stats.impressions else "—"
    return translate(
        "panel.ads.stats_body",
        locale,
        total=stats.total_ads,
        active=stats.active_ads,
        impressions=stats.impressions,
        clicks=stats.clicks,
        ctr=ctr,
    )


async def _settings_text(settings: SettingsService, translate: Translator, locale: str) -> str:
    current = {view.key: view.value for view in await settings.list_all()}
    lines = [
        translate("panel.settings.list_header", locale),
        translate("panel.settings.list_subheader", locale),
        "",
    ]
    for field in SETTING_FIELDS:
        label = translate(field.label_key, locale)
        lines.append(f"• {label}: <b>{escape(current.get(field.key, '—'))}</b>")
    return "\n".join(lines)


def _settings_info_text(index: int | None, translate: Translator, locale: str) -> str:
    """Read-only info for the Cache / Languages submenu items (no LOCKED key to edit)."""
    if index == 0:
        return translate("panel.settings.info.cache_body", locale)
    if index == 1:
        languages = ", ".join(
            f"{meta.native_name} ({meta.code})" for meta in list_enabled_locales()
        )
        return translate(
            "panel.settings.info.languages_body", locale, languages=languages, default=locale
        )
    return translate("panel.settings.info.fallback", locale)


async def _jobs_text(
    admin: AdminService,
    *,
    status: str | None = None,
    title_key: str = "panel.jobs.default_title",
    translate: Translator,
    locale: str,
) -> str:
    jobs = await admin.list_jobs(limit=_LIST_LIMIT, status=status)
    title = translate(title_key, locale)
    if not jobs:
        return translate("panel.jobs.empty", locale, title=title)
    lines = [title, ""]
    for job in jobs:
        lines.append(
            f"<code>{escape(job.id[:8])}</code> · {escape(job.status)} · "
            f"{escape(job.format)}/{escape(job.quality)}"
        )
    return "\n".join(lines)


async def _errors_text(admin: AdminService, translate: Translator, locale: str) -> str:
    errors = await admin.browse_errors(limit=_LIST_LIMIT)
    if not errors:
        return translate("panel.errors.empty", locale)
    lines = [translate("panel.errors.title", locale), ""]
    for err in errors:
        lines.append(
            f"<code>{err.created_at:%m-%d %H:%M}</code> · "
            f"{escape(err.error_type)}: {escape(err.message[:60])}"
        )
    return "\n".join(lines)


async def _queue_text(queue: QueueService, translate: Translator, locale: str) -> str:
    depth, active = await queue.depth(), await queue.active_count()
    return translate("panel.downloads.body", locale, depth=depth, active=active)


async def _system_text(
    users: UserService,
    settings: SettingsService,
    queue: QueueService,
    translate: Translator,
    locale: str,
) -> str:
    stats = await users.get_stats()
    depth, active = await queue.depth(), await queue.active_count()
    maintenance = await settings.get_view("maintenance_mode")
    return translate(
        "panel.system.body",
        locale,
        maintenance=escape(maintenance.value if maintenance else "—"),
        users=stats.total_users,
        downloads=stats.total_downloads,
        depth=depth,
        active=active,
    )
