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

import csv
import datetime
import io
import json
from collections.abc import Callable, Sequence
from html import escape
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.callbacks.factory import CallbackSigner, ParsedPanel
from bot.filters.panel_filter import PanelFilter
from bot.filters.role_filter import RoleFilter, StaffFilter
from bot.handlers import admin_wizard
from bot.keyboards.admin_panel import (
    build_ad_conflict_confirm,
    build_ad_detail,
    build_ad_language_categories,
    build_ad_list,
    build_broadcast_detail,
    build_broadcast_list,
    build_confirm,
    build_export_formats,
    build_input_prompt,
    build_language_chooser,
    build_main_menu,
    build_placement_list,
    build_platform_stats,
    build_section_menu,
    build_setting_stepper,
    build_settings_menu,
    build_template_detail,
    build_template_list,
    build_user_detail,
    build_user_list,
)
from bot.keyboards.language_select import build_language_picker
from bot.panel import ui
from bot.panel.registry import (
    PLACEMENT_OPTIONS,
    SECTIONS,
    SETTING_FIELDS,
    SettingField,
    placement_option,
    setting_field,
)
from bot.panel.states import PanelStates
from core.i18n import Translator, list_enabled_locales
from core.logging import get_logger
from domain.entities.user import UserSnapshot
from domain.enums import UserRole
from services.ad_service import AdDetailedStats, AdService
from services.admin_notification_service import AdminNotificationService
from services.admin_service import AdminService
from services.audience_service import AudienceService
from services.broadcast_service import BroadcastService, InvalidBroadcastError
from services.queue_service import QueueService
from services.referral_service import ReferralService
from services.settings_service import (
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingsService,
)
from services.template_service import TEMPLATE_DEFS, TemplateService
from services.user_health import UserHealthChecker
from services.user_service import UserService

router = Router(name="admin_panel")
_log = get_logger("bot.handlers.admin_panel")

UserServiceFactory = Callable[[AsyncSession], UserService]
SettingsServiceFactory = Callable[[AsyncSession], SettingsService]
AdminServiceFactory = Callable[[AsyncSession], AdminService]
ReferralServiceFactory = Callable[[AsyncSession], ReferralService]
HealthCheckerFactory = Callable[[Bot], UserHealthChecker]
AdServiceFactory = Callable[[AsyncSession], AdService]
BroadcastServiceFactory = Callable[[AsyncSession], BroadcastService]
AudienceServiceFactory = Callable[[AsyncSession], AudienceService]
AdminNotificationFactory = Callable[[AsyncSession], AdminNotificationService]

OwnerFilter = RoleFilter(UserRole.OWNER)

_OWNER_ONLY_SECTIONS = frozenset(section.code for section in SECTIONS if section.owner_only)
_LIST_LIMIT = 20
# Mirrors core.error_report.Severity — kept as a plain map so the panel layer does not
# import the reporting module for four emoji.
_SEVERITY_ICON = {
    "critical": "🔴",
    "error": "🟠",
    "warning": "🟡",
    "info": "🔵",
}

# Platform-analytics period filter, indexed by the compact callback ``arg`` (13.3).
_PERIODS: tuple[str, ...] = ("today", "week", "month", "all")


# --- entry commands -------------------------------------------------------
@router.message(Command("admin"), StaffFilter)
async def open_panel(
    message: Message,
    session: AsyncSession,
    user: UserSnapshot,
    user_service_factory: UserServiceFactory,
    queue_service: QueueService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    text = await _main_menu_text(user_service_factory(session), queue_service, translate, locale)
    await message.answer(text, reply_markup=build_main_menu(user.role, callback_signer, locale))


async def _main_menu_text(
    users: UserService, queue: QueueService, translate: Translator, locale: str
) -> str:
    """The main-menu live dashboard: 5 key metrics before the owner taps anything (§2.5)."""
    stats = await users.get_stats()
    depth, active = await queue.depth(), await queue.active_count()

    def label(name: str) -> str:
        return translate(f"panel.stats.label.{name}", locale)

    return "\n".join(
        [
            ui.header(translate("panel.main_title", locale), icon=ui.emoji("stats")),
            "",
            ui.metric(ui.emoji("members"), label("members"), stats.total_users),
            ui.metric(ui.emoji("fire"), label("active_24h"), stats.active_24h),
            ui.metric(ui.emoji("download"), label("downloads"), stats.total_downloads),
            ui.metric(ui.emoji("queue"), label("queue"), f"{depth} / {active}"),
            ui.metric(ui.emoji("premium"), label("premium"), stats.premium_users),
            ui.metric(ui.badge("banned"), label("banned"), stats.banned_users),
            "",
            ui.footer(),
        ]
    )


async def main_menu_view(
    users: UserService,
    queue: QueueService,
    role: UserRole,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """(text, keyboard) for the panel home — reused to reopen the panel after a language
    change (item #7), so the acting staff member lands back where they were."""
    return await _main_menu_text(users, queue, translate, locale), build_main_menu(
        role, signer, locale
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
    referral_service_factory: ReferralServiceFactory,
    broadcast_service_factory: BroadcastServiceFactory,
    template_service: TemplateService,
    queue_service: QueueService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    # The compose wizard's Cancel is a read-tier action (``w/cx``): route it to the wizard's
    # own cancel *before* the blanket state.clear() below, so it can read the kind and return
    # to the right section menu instead of silently wiping the wizard (#5).
    if panel.section == "w":
        if panel.action == "cx":
            await admin_wizard.cancel(callback, state, callback_signer, translate, locale)
        else:
            await callback.answer()
        return
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
        referral_service_factory,
        template_service,
        queue_service,
        broadcast_service_factory,
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
    template_service: TemplateService,
    health_checker_factory: HealthCheckerFactory,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
    admin_notification_factory: AdminNotificationFactory | None = None,
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
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.ads.create_pick_language", locale),
                build_language_chooser("a", "crl", callback_signer, locale),
            )
        await callback.answer()
        return
    if panel.section == "a" and panel.action == "crl" and panel.arg is not None:
        locales = list_enabled_locales()
        if 0 <= panel.arg < len(locales):
            lang = locales[panel.arg].code
            await admin_wizard.start(
                callback, state, callback_signer, translate, locale,
                kind="ad", target_language=lang,
            )
        else:
            await callback.answer()
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
    if panel.section == "b" and panel.action in ("cen", "car"):
        lang = "en" if panel.action == "cen" else "ar"
        await admin_wizard.start(
            callback,
            state,
            callback_signer,
            translate,
            locale,
            kind="broadcast",
            target_language=lang,
        )
        return
    if panel.section == "b" and panel.action == "pbd" and panel.arg is not None:
        bc_svc = broadcast_service_factory(session)
        bc = await bc_svc.get_broadcast(panel.arg)
        if bc is None or bc.status != "draft":
            await callback.answer(translate("panel.broadcast.not_draft", locale), show_alert=True)
            return
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.broadcast.publish_confirm", locale, id=bc.id),
                build_confirm(
                    callback_signer,
                    locale,
                    confirm=("b", "pbc", panel.arg, None),
                    cancel=("b", "inf", panel.arg),
                ),
            )
        await callback.answer()
        return
    if panel.section == "b" and panel.action == "pbc" and panel.arg is not None:
        try:
            bc = await broadcast_service_factory(session).publish_draft(panel.arg)
        except InvalidBroadcastError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        if admin_notification_factory is not None:
            await admin_notification_factory(session).notify_broadcast_published(
                by_admin=user, broadcast_id=bc.id, expected_total=bc.expected_total
            )
        await callback.answer(
            translate("panel.wizard.broadcast_published", locale, id=bc.id, count=bc.expected_total)
        )
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                _broadcast_detail_text(bc, translate, locale),
                build_broadcast_detail(bc, callback_signer, locale),
            )
        return
    if panel.section == "b" and panel.action == "bde" and panel.arg is not None:
        bc = await broadcast_service_factory(session).get_broadcast(panel.arg)
        if bc is None:
            await callback.answer(translate("panel.broadcast.not_found", locale), show_alert=True)
            return
        if bc.status in ("pending", "in_progress"):
            await callback.answer(
                translate("panel.broadcast.cannot_delete_active", locale), show_alert=True
            )
            return
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.broadcast.delete_confirm", locale, id=bc.id),
                build_confirm(
                    callback_signer,
                    locale,
                    confirm=("b", "bdc", panel.arg, None),
                    cancel=("b", "inf", panel.arg),
                ),
            )
        await callback.answer()
        return
    if panel.section == "b" and panel.action == "bdc" and panel.arg is not None:
        try:
            deleted = await broadcast_service_factory(session).delete_broadcast(panel.arg)
        except InvalidBroadcastError as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        toast = (
            translate("panel.broadcast.deleted", locale, id=panel.arg)
            if deleted
            else translate("panel.broadcast.not_found", locale)
        )
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                _broadcast_text(translate, locale),
                build_language_chooser("b", "lsl", callback_signer, locale),
            )
        await callback.answer(toast)
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
    if panel.section == "m" and panel.action in ("chk", "pgb", "pgd", "pgbc", "pgdc"):  # 13.5
        await _moderation_health_write(
            callback,
            panel,
            user_service_factory(session),
            health_checker_factory,
            callback_signer,
            translate,
            locale,
        )
        return
    if panel.section == "u" and panel.action in ("exp", "exc", "exj", "imp"):  # subscribers (13.6)
        await _subscribers_write(
            callback,
            panel,
            user_service_factory(session),
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
    if panel.section == "t" and panel.action == "csv":  # Platform analytics CSV export (13.3)
        await _platform_export(callback, admin_service_factory(session), translate, locale)
        return
    if panel.section == "tp":  # Message templates edit / reset (Sprint 13.8)
        await _templates_write(
            callback, panel, template_service, user, callback_signer, state, translate, locale
        )
        return
    if panel.section == "a" and panel.action == "plt" and panel.arg is not None:
        opt = placement_option(panel.arg)
        if opt is None:
            await callback.answer()
            return
        settings = settings_service_factory(session)
        key = f"ad_placement_{opt.code}_enabled"
        try:
            current: bool = await settings.get(key)
        except SettingNotFoundError:
            current = False
        new_val = "false" if current else "true"
        await settings.set_validated(key, new_val, updated_by=user.id)
        states = await _placement_states(settings)
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                _placements_text(states, translate, locale),
                build_placement_list(states, callback_signer, locale),
            )
        await callback.answer()
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
    result = await _apply_user_action(users, action, tid, translate, locale, by_admin=actor)
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
    users: UserService,
    action: str,
    tid: int,
    translate: Translator,
    locale: str,
    *,
    by_admin: UserSnapshot | None = None,
) -> tuple[UserSnapshot, str] | None:
    """Perform a (possibly already-confirmed) user write. Returns (snapshot, toast) or None."""
    if action == "ubn":
        snap = await users.unban(tid, by_admin=by_admin)
        return (snap, translate("panel.users.toast.unbanned", locale)) if snap else None
    if action == "up":
        snap = await users.set_premium(tid, is_premium=True)
        return (snap, translate("panel.users.toast.premium_granted", locale)) if snap else None
    if action == "banc":
        snap = await users.ban(tid, by_admin=by_admin)
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
    # Values are passed RAW: ui.card / ui.metric HTML-escape internally.
    def lbl(name: str) -> str:
        return translate(f"panel.users.detail.label.{name}", locale)

    if snap.is_banned:
        status = translate("panel.users.detail.banned_status", locale) + (
            f" — {snap.ban_reason}" if snap.ban_reason else ""
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
    profile = ui.card(
        translate("panel.users.detail.title", locale),
        [
            (lbl("name"), snap.first_name or "—"),
            (lbl("username"), f"@{snap.username}" if snap.username else "—"),
            (lbl("id"), str(snap.telegram_id)),
            (lbl("role"), f"{ui.role_icon(snap.role.value)} {snap.role.value}"),
            (lbl("status"), status),
            (lbl("premium"), premium),
            (lbl("language"), snap.language or "—"),
        ],
        icon=ui.role_icon(snap.role.value),
    )
    activity = "\n".join(
        [
            ui.divider(),
            "",
            ui.metric(ui.emoji("download"), lbl("downloads"), snap.total_downloads),
            ui.metric(
                ui.emoji("new"), lbl("today"), f"{snap.daily_download_count} / {daily_limit}"
            ),
            ui.metric(ui.emoji("chart"), lbl("history"), history_count),
            ui.metric(ui.emoji("queue"), lbl("active_job"), active_jobs),
            ui.metric(ui.emoji("calendar"), lbl("joined"), _fmt_dt(snap.created_at)),
            ui.metric(ui.emoji("clock"), lbl("last_seen"), _fmt_dt(snap.last_activity_at)),
        ]
    )
    return f"{profile}\n\n{activity}"


def _fmt_dt(value: datetime.datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value is not None else "—"


def _users_list_text(rows: list[UserSnapshot], translate: Translator, locale: str) -> str:
    """Tappable Users list header rendered through ui.py (rows are buttons) (13.2)."""
    header = ui.header(translate("panel.users.list_title", locale), icon=ui.emoji("users"))
    if not rows:
        return f"{header}\n\n{translate('panel.users.none_yet', locale)}"
    return "\n".join(
        [
            header,
            "",
            ui.metric(ui.emoji("members"), translate("panel.users.count_label", locale), len(rows)),
            f"  {translate('panel.users.tap_hint', locale)}",
            "",
            ui.footer(),
        ]
    )


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
    referral_factory: ReferralServiceFactory,
    template_service: TemplateService,
    queue: QueueService,
    broadcast_factory: BroadcastServiceFactory,
    translate: Translator,
    locale: str,
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Map a verified read callback to (message text, keyboard). None → just ack."""
    section, action = panel.section, panel.action
    role = user.role
    if section == "mn":
        text = await _main_menu_text(user_factory(session), queue, translate, locale)
        return text, build_main_menu(role, signer, locale)
    if section == "l":  # personal language preference (Sprint 11.5) — same picker as /start
        # origin "p" so the pick reopens the panel home in the new locale (#7).
        return translate("language.picker_prompt", locale), build_language_picker(signer, "p")
    if section == "s":
        if action == "inf":
            return _settings_info_text(panel.arg, translate, locale), build_settings_menu(
                role, signer, locale
            )
        return await _settings_text(
            settings_factory(session), translate, locale
        ), build_settings_menu(role, signer, locale)
    if section == "t":
        if action == "stt":  # platform-analytics sub-screen (Sprint 13.3)
            period = (
                _PERIODS[panel.arg]
                if panel.arg is not None and 0 <= panel.arg < len(_PERIODS)
                else "all"
            )
            text = await _platform_stats_text(admin_factory(session), period, translate, locale)
            return text, build_platform_stats(
                signer, locale, period_index=_PERIODS.index(period), role=role
            )
        return await _stats_text(
            user_factory(session), queue, translate, locale
        ), build_section_menu("t", role, signer, locale)
    if section == "r":  # Referral analytics dashboard (Sprint 13.7)
        text = await _referral_dashboard_text(referral_factory(session), translate, locale)
        return text, build_section_menu("r", role, signer, locale)
    if section == "tp":  # Message templates — pick locale, then list/detail (Sprint 13.8 / 14)
        if action == "ls" and panel.arg is not None:  # list for the chosen locale (arg=locale idx)
            target = _locale_at(panel.arg, locale)
            views = await template_service.list_all(target)
            return _templates_list_text(translate, locale, target), build_template_list(
                views, signer, locale, panel.arg
            )
        if action == "inf" and panel.arg is not None and 0 <= panel.arg < len(TEMPLATE_DEFS):
            target = _locale_at(panel.value, locale)
            return await _template_detail_view(
                template_service, panel.arg, signer, translate, locale, target, panel.value
            )
        # Section entry (op) or any fallthrough: choose the language first (data-driven).
        return _templates_pick_language_text(translate, locale), build_language_chooser(
            "tp", "ls", signer, locale
        )
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
            all_ads = await ads.list_ads()
            counts = _language_counts(all_ads)
            return _ads_list_text(all_ads, translate, locale), build_ad_language_categories(
                counts, signer, locale
            )
        if action == "lsl" and panel.arg is not None:
            locales = list_enabled_locales()
            if 0 <= panel.arg < len(locales):
                lang: str | None = locales[panel.arg].code
            elif panel.arg == len(locales):
                lang = None
            else:
                return translate("panel.ads.section_body", locale), build_section_menu(
                    "a", role, signer, locale
                )
            filtered = await ads.list_ads_by_language(lang)
            return _ads_list_text(filtered, translate, locale), build_ad_list(
                filtered, signer, locale
            )
        if action == "ast" and panel.arg is not None:
            stats = await ads.detailed_stats(panel.arg)
            if stats is None:
                return translate(
                    "panel.ads.not_found", locale
                ), build_section_menu("a", role, signer, locale)
            broadcasts = broadcast_factory(session)
            bc_sent, bc_last = await broadcasts.totals_for_ad(
                panel.arg
            )
            return _ad_stats_text(
                stats, bc_sent, bc_last, translate, locale
            ), build_ad_detail(
                await ads.get(panel.arg), role, signer, locale
            )
        if action == "pl":
            settings = settings_factory(session)
            states = await _placement_states(settings)
            return _placements_text(
                states, translate, locale
            ), build_placement_list(states, signer, locale)
        if action == "stt":
            return await _overall_stats_text(
                ads, translate, locale
            ), build_section_menu("a", role, signer, locale)
        return translate("panel.ads.section_body", locale), build_section_menu(
            "a", role, signer, locale
        )
    if section == "b":
        if action == "ls":
            return _broadcast_text(translate, locale), build_language_chooser(
                "b", "lsl", signer, locale
            )
        if action == "lsl" and panel.arg is not None:
            from bot.callbacks.paging import decode_filter_page

            lang_index, page = decode_filter_page(panel.arg)
            locales = list_enabled_locales()
            bc_lang: str | None
            if 0 <= lang_index < len(locales):
                bc_lang = locales[lang_index].code
            elif lang_index == len(locales):
                bc_lang = None
            else:
                return _broadcast_text(translate, locale), build_section_menu(
                    "b", role, signer, locale
                )
            bc_svc = broadcast_factory(session)
            rows, pg, has_prev, has_next = await bc_svc.list_saved_page(
                bc_lang, page=page, page_size=5
            )
            return _broadcast_list_text(rows, translate, locale), build_broadcast_list(
                rows, signer, locale,
                lang_index=lang_index, page=pg, has_prev=has_prev, has_next=has_next,
            )
        if action == "inf" and panel.arg is not None:
            broadcast = await broadcast_factory(session).get_broadcast(panel.arg)
            if broadcast is not None:
                return _broadcast_detail_text(broadcast, translate, locale), build_broadcast_detail(
                    broadcast, signer, locale
                )
        return _broadcast_text(translate, locale), build_section_menu("b", role, signer, locale)
    if section == "m":
        users_svc = user_factory(session)
        if action == "lsb":  # blocked-bot list (Sprint 13.5)
            rows = await users_svc.list_blocked(limit=_LIST_LIMIT)
            return _health_list_text(
                rows, "panel.health.blocked_title", "panel.health.blocked_empty", translate, locale
            ), build_section_menu("m", role, signer, locale)
        if action == "lsd":  # deleted-account list (Sprint 13.5)
            rows = await users_svc.list_deleted(limit=_LIST_LIMIT)
            return _health_list_text(
                rows, "panel.health.deleted_title", "panel.health.deleted_empty", translate, locale
            ), build_section_menu("m", role, signer, locale)
        return await _users_text(
            users_svc, banned_only=True, translate=translate, locale=locale
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


def _platform_name(code: str, translate: Translator, locale: str) -> str:
    """Localized platform display name, falling back to the raw code (13.3)."""
    key = f"platform.{code.lower()}"
    name = translate(key, locale)
    return code if name == key else name


async def _platform_stats_text(
    admin: AdminService, period: str, translate: Translator, locale: str
) -> str:
    """Sparkline breakdown of downloads per platform for a period (Sprint 13.3)."""
    view = await admin.get_platform_stats(period=period)
    title = translate("panel.platforms.title", locale)
    period_label = translate(f"panel.platforms.filter.{period}", locale)
    lines = [ui.header(f"{title} · {period_label}", icon=ui.emoji("chart")), ""]
    if not view.platforms:
        lines.append(translate("panel.platforms.empty", locale))
        lines += ["", ui.footer()]
        return "\n".join(lines)
    max_count = max(p.count for p in view.platforms)
    for entry in view.platforms:
        name = _platform_name(entry.platform, translate, locale)
        lines.append(f"{ui.sparkline(name, entry.count, max_count)}  {entry.share_pct:.1f}%")
    lines += [
        ui.divider(),
        ui.metric(ui.emoji("chart"), translate("panel.platforms.total", locale), view.total),
        "",
        ui.footer(),
    ]
    return "\n".join(lines)


def _platform_report_csv(report: Any, translate: Translator, locale: str) -> bytes:
    """Render the multi-period platform report to CSV bytes (Sprint 13.3)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Platform", "Today", "This Week", "This Month", "All Time", "Share %"])
    for row in report.rows:
        writer.writerow(
            [
                _platform_name(row.platform, translate, locale),
                row.today,
                row.week,
                row.month,
                row.all_time,
                f"{row.share_pct:.1f}",
            ]
        )
    return buffer.getvalue().encode("utf-8")


async def _platform_export(
    callback: CallbackQuery, admin: AdminService, translate: Translator, locale: str
) -> None:
    """Generate and send the platform-analytics CSV as a document (Sprint 13.3)."""
    report = await admin.get_platform_report()
    data = _platform_report_csv(report, translate, locale)
    date = datetime.datetime.now(datetime.UTC).date().isoformat()
    document = BufferedInputFile(data, filename=f"download_stats_{date}.csv")
    if callback.bot is not None and isinstance(callback.message, Message):
        await callback.bot.send_document(callback.message.chat.id, document)
    await callback.answer(translate("panel.platforms.exported", locale))


async def _referral_dashboard_text(
    referral: ReferralService, translate: Translator, locale: str
) -> str:
    """Referral analytics dashboard: totals, period breakdowns, top-5 leaderboard (13.7)."""
    dash = await referral.get_dashboard()

    def label(name: str) -> str:
        return translate(f"panel.referral.{name}", locale)

    lines = [
        ui.header(label("title"), icon=ui.emoji("referral")),
        "",
        ui.metric(ui.emoji("chart"), label("total"), dash.total_referrals),
        ui.metric(ui.emoji("new"), label("today"), dash.referrals_today),
        ui.metric(ui.emoji("calendar"), label("week"), dash.referrals_week),
        ui.metric(ui.emoji("calendar"), label("month"), dash.referrals_month),
        ui.metric(ui.emoji("gift"), label("rewards"), dash.total_rewards_granted),
    ]
    if dash.top_referrers:
        lines += ["", ui.divider(), f"  {ui.emoji('trophy')} {label('top')}", ""]
        max_invites = max(entry.invite_count for entry in dash.top_referrers)
        for rank, entry in enumerate(dash.top_referrers, start=1):
            handle = (
                f"@{entry.username}" if entry.username else (entry.first_name or str(entry.user_id))
            )
            lines.append(f"  {rank}. {ui.sparkline(handle, entry.invite_count, max_invites)}")
    lines += ["", ui.footer()]
    return "\n".join(lines)


def _health_list_text(
    rows: list[UserSnapshot], title_key: str, empty_key: str, translate: Translator, locale: str
) -> str:
    """Render a blocked / deleted user list with the ui.py header + tappable-free rows (13.5)."""
    header = ui.header(translate(title_key, locale, count=len(rows)), icon=ui.emoji("moderation"))
    if not rows:
        return f"{header}\n\n{translate(empty_key, locale)}"
    return "\n".join([header, "", *(_user_row(snap) for snap in rows)])


async def _moderation_health_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    users: UserService,
    checker_factory: HealthCheckerFactory,
    signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Check-status sweep and blocked/deleted purges (destructive → confirm) (13.5)."""
    menu = build_section_menu("m", UserRole.OWNER, signer, locale)
    if panel.action == "chk":  # run the Telegram-API status sweep
        if callback.bot is None or not isinstance(callback.message, Message):
            await callback.answer()
            return
        await _safe_edit(callback.message, translate("panel.health.checking", locale), menu)
        await callback.answer()
        report = await checker_factory(callback.bot).check_all()
        await _safe_edit(
            callback.message,
            translate(
                "panel.health.result",
                locale,
                checked=report.total_checked,
                active=report.active,
                blocked=report.blocked,
                deleted=report.deleted,
                errors=report.errors,
                seconds=f"{report.duration_seconds:.1f}",
            ),
            menu,
        )
        return
    if panel.action in ("pgb", "pgd"):  # destructive → confirm screen
        confirmed = "pgbc" if panel.action == "pgb" else "pgdc"
        verb_key = (
            "panel.health.purge_blocked_verb"
            if panel.action == "pgb"
            else "panel.health.purge_deleted_verb"
        )
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.health.purge_confirm", locale, what=translate(verb_key, locale)),
                build_confirm(
                    signer, locale, confirm=("m", confirmed, None, None), cancel=("m", "op", None)
                ),
            )
        await callback.answer()
        return
    # confirmed purge
    removed = await (users.purge_blocked() if panel.action == "pgbc" else users.purge_deleted())
    toast = translate("panel.health.purged", locale, count=removed)
    if isinstance(callback.message, Message):
        await _safe_edit(callback.message, toast, menu)
    await callback.answer(toast)


def _locale_at(index: int | None, fallback: str) -> str:
    """Resolve a ``list_enabled_locales()`` index to its code (data-driven); fallback if invalid."""
    if index is not None:
        locales = list_enabled_locales()
        if 0 <= index < len(locales):
            return locales[index].code
    return fallback


def _templates_pick_language_text(translate: Translator, locale: str) -> str:
    return "\n".join(
        [
            ui.header(translate("panel.templates.title", locale), icon=ui.emoji("templates")),
            "",
            translate("panel.templates.pick_language", locale),
        ]
    )


def _templates_list_text(
    translate: Translator, locale: str, target_locale: str | None = None
) -> str:
    lines = [
        ui.header(translate("panel.templates.title", locale), icon=ui.emoji("templates")),
        "",
        translate("panel.templates.subtitle", locale),
    ]
    if target_locale is not None:
        name = next(
            (m.native_name for m in list_enabled_locales() if m.code == target_locale),
            target_locale,
        )
        lines += ["", ui.metric("🌐", translate("panel.templates.language_label", locale), name)]
    return "\n".join(lines)


def _template_detail_text(
    definition: Any,
    content: str,
    is_custom: bool,
    translate: Translator,
    locale: str,
    *,
    buttons: list[dict[str, str]] | None = None,
) -> str:
    """Edit screen body: full template content, placeholder legend, example, buttons."""
    from services.template_service import TemplateDef

    defn: TemplateDef = definition
    status = translate(
        "panel.templates.status_custom" if is_custom else "panel.templates.status_default", locale
    )
    lines = [
        ui.header(
            translate("panel.templates.edit_title", locale, template=defn.key),
            icon=ui.emoji("note"),
        ),
        "",
        f"  {translate('panel.templates.content_label', locale)}",
        f"<blockquote>{escape(content) or '—'}</blockquote>",
        "",
        ui.metric(ui.emoji("check"), translate("panel.templates.status", locale), status),
    ]
    if defn.placeholder_help:
        lines.append("")
        lines.append(f"  {translate('panel.templates.placeholder_legend', locale)}")
        for name, example in defn.placeholder_help:
            lines.append(f"  <code>{{{name}}}</code> → e.g. {escape(example)}")
        lines.append("")
        lines.append(f"  {translate('panel.templates.example_label', locale)}")
        try:
            example_vals = dict(defn.placeholder_help)
            lines.append(f"  <i>{escape(content.format(**example_vals))}</i>")
        except (KeyError, IndexError, ValueError):
            lines.append(f"  {translate('panel.templates.example_error', locale)}")
    if defn.allow_buttons:
        btn_text = (
            ", ".join(escape(b.get("text", "?")) for b in buttons)
            if buttons
            else translate("panel.templates.buttons_none", locale)
        )
        lines.append("")
        lines.append(
            ui.metric(
                ui.emoji("settings"),
                translate("panel.templates.buttons_label", locale),
                btn_text,
            )
        )
    return "\n".join(lines)


async def _template_detail_view(
    template_service: TemplateService,
    index: int,
    signer: CallbackSigner,
    translate: Translator,
    ui_locale: str,
    target_locale: str,
    locale_index: int | None,
) -> tuple[str, InlineKeyboardMarkup]:
    """Build a template's edit screen for ``target_locale`` (labels rendered in ``ui_locale``)."""
    definition = TEMPLATE_DEFS[index]
    content = template_service.full_content(definition.key, target_locale)
    is_custom = await template_service.get(definition.key, target_locale) is not None
    buttons = (
        template_service.buttons_for(definition.key, target_locale)
        if definition.allow_buttons
        else None
    )
    text = _template_detail_text(
        definition, content or "", is_custom, translate, ui_locale, buttons=buttons
    )
    return text, build_template_detail(
        index,
        is_custom=is_custom,
        allow_buttons=definition.allow_buttons,
        signer=signer,
        locale=ui_locale,
        locale_index=locale_index,
    )


async def _templates_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    template_service: TemplateService,
    actor: UserSnapshot,
    signer: CallbackSigner,
    state: FSMContext,
    translate: Translator,
    locale: str,
) -> None:
    """Edit content (arm FSM), reset-to-default (confirm), or apply a confirmed reset (13.8)."""
    index = panel.arg
    if index is None or not (0 <= index < len(TEMPLATE_DEFS)):
        await callback.answer()
        return
    definition = TEMPLATE_DEFS[index]
    loc_index = panel.value  # chosen target-locale index (Sprint 14), threaded via value
    target = _locale_at(loc_index, locale)
    if panel.action == "ed":  # arm the content-edit FSM
        if isinstance(callback.message, Message):
            await state.set_state(PanelStates.template_edit)
            await state.update_data(
                key=definition.key,
                locale=target,  # edit the CHOSEN locale's copy, not the admin's UI locale
                locale_index=loc_index,
                index=index,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
            await _safe_edit(
                callback.message,
                translate("panel.templates.edit_prompt", locale, template=definition.key),
                build_input_prompt(
                    signer, locale, back=("tp", "ls", loc_index), cancel=("tp", "ls", loc_index)
                ),
            )
        await callback.answer()
        return
    if panel.action == "edb" and definition.allow_buttons:  # arm button-edit FSM
        if isinstance(callback.message, Message):
            await state.set_state(PanelStates.template_button_edit)
            await state.update_data(
                key=definition.key,
                locale=target,
                locale_index=loc_index,
                index=index,
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
            await _safe_edit(
                callback.message,
                translate("panel.templates.buttons_prompt", locale),
                build_input_prompt(
                    signer, locale, back=("tp", "ls", loc_index), cancel=("tp", "ls", loc_index)
                ),
            )
        await callback.answer()
        return
    if panel.action == "rs":  # confirm reset-to-default
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.templates.reset_confirm", locale, template=definition.key),
                build_confirm(
                    signer,
                    locale,
                    confirm=("tp", "rsc", index, loc_index),
                    cancel=("tp", "ls", loc_index),
                ),
            )
        await callback.answer()
        return
    if panel.action == "rsc":  # confirmed reset
        await template_service.reset(definition.key, target)
        text, markup = await _template_detail_view(
            template_service, index, signer, translate, locale, target, loc_index
        )
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, text, markup)
        await callback.answer(translate("panel.templates.reset_done", locale))
        return
    await callback.answer()


@router.message(PanelStates.template_edit, OwnerFilter)
async def on_template_edit(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: UserSnapshot,
    template_service: TemplateService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Capture the typed template content, persist it, and re-render the edit screen (13.8)."""
    data = await state.get_data()
    key, tlocale, index = data.get("key"), data.get("locale"), data.get("index")
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    if (
        not isinstance(key, str)
        or not isinstance(tlocale, str)
        or not isinstance(index, int)
        or chat_id is None
        or message_id is None
    ):
        await state.clear()
        return
    content = (message.text or "").strip()
    if not content:
        await message.reply(translate("panel.templates.empty_content", locale))
        return
    defn = template_service.definition(key)
    if defn is not None:
        unknown = TemplateService.validate_placeholders(content, defn)
        if unknown:
            allowed = ", ".join(f"{{{p}}}" for p in defn.placeholders) or "—"
            await message.reply(
                translate(
                    "panel.templates.unknown_placeholders",
                    locale,
                    names=", ".join(f"{{{n}}}" for n in unknown),
                    allowed=allowed,
                )
            )
            return
    await state.clear()
    await template_service.set(key, tlocale, content, updated_by=user.id)
    loc_index = data.get("locale_index")
    text, markup = await _template_detail_view(
        template_service,
        index,
        callback_signer,
        translate,
        locale,
        tlocale,
        loc_index if isinstance(loc_index, int) else None,
    )
    await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


@router.message(PanelStates.template_button_edit, OwnerFilter)
async def on_template_button_edit(
    message: Message,
    state: FSMContext,
    bot: Bot,
    user: UserSnapshot,
    template_service: TemplateService,
    callback_signer: CallbackSigner,
    translate: Translator,
    locale: str,
) -> None:
    """Parse button lines (Text | url), validate, and persist."""
    data = await state.get_data()
    key, tlocale, index = data.get("key"), data.get("locale"), data.get("index")
    chat_id, message_id = data.get("chat_id"), data.get("message_id")
    if (
        not isinstance(key, str)
        or not isinstance(tlocale, str)
        or not isinstance(index, int)
        or chat_id is None
        or message_id is None
    ):
        await state.clear()
        return
    raw = (message.text or "").strip()
    if raw == "-":
        buttons: list[dict[str, str]] | None = None
    else:
        buttons = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                await message.reply(translate("panel.templates.buttons_invalid", locale))
                return
            text_part, url_part = parts[0].strip(), parts[1].strip()
            if not text_part or not url_part.startswith(("http://", "https://")):
                await message.reply(translate("panel.templates.buttons_invalid", locale))
                return
            buttons.append({"text": text_part, "url": url_part})
        if len(buttons) > 3:
            await message.reply(translate("panel.templates.buttons_invalid", locale))
            return
        if not buttons:
            buttons = None
    await state.clear()
    await template_service.set_buttons(key, tlocale, buttons)
    loc_index = data.get("locale_index")
    text, markup = await _template_detail_view(
        template_service,
        index,
        callback_signer,
        translate,
        locale,
        tlocale,
        loc_index if isinstance(loc_index, int) else None,
    )
    await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup)


async def _subscribers_write(
    callback: CallbackQuery,
    panel: ParsedPanel,
    users: UserService,
    signer: CallbackSigner,
    state: FSMContext,
    translate: Translator,
    locale: str,
) -> None:
    """Subscriber export (format picker → document) and import (arm file upload) (13.6)."""
    if panel.action == "exp":  # show the CSV / JSON format picker
        if isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                translate("panel.users.export_prompt", locale),
                build_export_formats(signer, locale),
            )
        await callback.answer()
        return
    if panel.action in ("exc", "exj"):  # generate + send the export document
        data, filename = await users.export_users("csv" if panel.action == "exc" else "json")
        if callback.bot is not None and isinstance(callback.message, Message):
            await callback.bot.send_document(
                callback.message.chat.id, BufferedInputFile(data, filename=filename)
            )
        await callback.answer(translate("panel.users.exported", locale))
        return
    # imp → arm the file-upload FSM; the next document is parsed and upserted
    if isinstance(callback.message, Message):
        await state.set_state(PanelStates.import_subscribers)
        await state.update_data(
            chat_id=callback.message.chat.id, message_id=callback.message.message_id
        )
        await _safe_edit(
            callback.message,
            translate("panel.users.import_prompt", locale),
            build_input_prompt(signer, locale, back=("u", "op", None), cancel=("u", "op", None)),
        )
    await callback.answer()


def _parse_subscribers(raw: bytes, filename: str) -> list[dict[str, Any]]:
    """Parse an uploaded ``.json`` / ``.csv`` subscriber file into row dicts (13.6)."""
    text = raw.decode("utf-8-sig", errors="replace")
    if filename.lower().endswith(".json"):
        payload = json.loads(text)
        rows = payload.get("users", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("json payload is not a user list")
        return [row for row in rows if isinstance(row, dict)]
    return list(csv.DictReader(io.StringIO(text)))


@router.message(PanelStates.import_subscribers, OwnerFilter)
async def on_import_subscribers(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    user_service_factory: UserServiceFactory,
    translate: Translator,
    locale: str,
) -> None:
    """Receive the uploaded subscriber file, parse it, and bulk-import (create-only)."""
    if message.document is None:
        await message.reply(translate("panel.users.import_need_file", locale))
        return  # keep the state so the next upload is still captured
    await state.clear()
    buffer = await bot.download(message.document)
    raw = buffer.read() if buffer is not None else b""
    try:
        rows = _parse_subscribers(raw, message.document.file_name or "")
    except (ValueError, json.JSONDecodeError):
        await message.reply(translate("panel.users.import_parse_error", locale))
        return
    result = await user_service_factory(session).import_users(rows)
    await message.reply(
        translate(
            "panel.users.import_result",
            locale,
            created=result.created,
            skipped=result.skipped,
            failed=result.failed,
        )
    )


async def _users_text(
    users: UserService, *, banned_only: bool, translate: Translator, locale: str
) -> str:
    """User / banned-user list rendered through the ui.py design system (Sprint 13.2)."""
    rows = await users.list_users(limit=_LIST_LIMIT)
    if banned_only:
        rows = [row for row in rows if row.is_banned]
    title_key = "panel.users.banned_list_title" if banned_only else "panel.users.list_title"
    header = ui.header(
        translate(title_key, locale), icon=ui.emoji("blocked" if banned_only else "users")
    )
    if not rows:
        empty = translate(
            "panel.users.none_banned" if banned_only else "panel.users.none_yet", locale
        )
        return f"{header}\n\n{empty}"
    return "\n".join([header, "", *(_user_row(row) for row in rows), "", ui.footer()])


def _user_row(snap: UserSnapshot) -> str:
    """A single list row: status/role glyph · id · @username · role (Sprint 13.2)."""
    username = f"@{escape(snap.username)}" if snap.username else "—"
    if snap.is_banned:
        marker = ui.badge("banned")
    elif snap.is_premium:
        marker = ui.emoji("premium")
    else:
        marker = ui.role_icon(snap.role.value)
    return f"{marker} <code>{snap.telegram_id}</code> · {username} · {escape(snap.role.value)}"


# Destructive / high-impact ad actions route through a confirm screen first.
_AD_CONFIRM = {
    "de": ("dec", "panel.verb.delete_ad"),
    "bc": ("bcc", "panel.verb.broadcast_all"),
}

# The high-visibility placement guarded by the "already-active" conflict warning (#9).
_POST_DOWNLOAD = "post_download"


def _ad_conflict_text(
    incoming: Any, existing: Sequence[Any], translate: Translator, locale: str
) -> str:
    """Warn before a second post-download ad goes live, naming both sides clearly (#9)."""
    active_lines = "\n".join(
        translate("panel.ads.conflict.active_row", locale, id=ad.id, title=escape(ad.title))
        for ad in existing
    )
    return "\n".join(
        [
            ui.header(translate("panel.ads.conflict.title", locale), icon=ui.emoji("ads")),
            "",
            translate("panel.ads.conflict.body", locale),
            "",
            translate("panel.ads.conflict.already_active", locale),
            active_lines,
            "",
            translate(
                "panel.ads.conflict.about_to_enable",
                locale,
                id=incoming.id,
                title=escape(incoming.title),
            ),
        ]
    )


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
        await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
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
    if action == "di":  # disable directly (never conflicts)
        if await ads.set_active(ad_id, False) is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(translate("panel.ads.disabled_toast", locale))
        return
    if action == "en":  # enable — warn first if a post-download ad is already active (#9)
        incoming = await ads.get(ad_id)
        if incoming is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        conflicts = (
            await ads.active_conflicts(_POST_DOWNLOAD, exclude_id=ad_id)
            if await ads.targets_placement(ad_id, _POST_DOWNLOAD)
            else []
        )
        if conflicts and isinstance(callback.message, Message):
            await _safe_edit(
                callback.message,
                _ad_conflict_text(incoming, conflicts, translate, locale),
                build_ad_conflict_confirm(
                    signer,
                    locale,
                    keep=("a", "enk", ad_id),
                    replace=("a", "enr", ad_id),
                    cancel=("a", "inf", ad_id),
                ),
            )
            await callback.answer()
            return
        await ads.set_active(ad_id, True)
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(translate("panel.ads.enabled_toast", locale))
        return
    if action == "enk":  # conflict resolution: keep both active
        if await ads.set_active(ad_id, True) is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(translate("panel.ads.conflict.kept_both_toast", locale))
        return
    if action == "enr":  # conflict resolution: replace the currently-active post-download ad(s)
        if await ads.get(ad_id) is None:
            await callback.answer(translate("panel.ads.not_found", locale), show_alert=True)
            return
        disabled = await ads.replace_active_on_placement(_POST_DOWNLOAD, keep_id=ad_id)
        await ads.set_active(ad_id, True)
        await _rerender_ad_detail(callback, ads, ad_id, actor.role, signer, translate, locale)
        await callback.answer(
            translate("panel.ads.conflict.replaced_toast", locale, count=len(disabled))
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
    """Ad detail rendered as a ui.card profile block (Sprint 13.2)."""
    state = translate(
        "panel.ads.state_active" if ad.is_active else "panel.ads.state_disabled", locale
    )
    ctr = f"{ad.clicks / ad.impressions * 100:.1f}%" if ad.impressions else "—"
    target = ad.target_role or translate("panel.ads.target_all", locale)

    def lbl(name: str) -> str:
        return translate(f"panel.ads.label.{name}", locale)

    return ui.card(
        f"{ad.title} (#{ad.id})",
        [
            (lbl("type"), str(ad.type)),
            (lbl("state"), state),
            (lbl("target"), str(target)),
            (lbl("priority"), str(ad.priority)),
            (lbl("frequency"), str(ad.show_every_n_downloads)),
            (lbl("impressions"), ui.number_fmt(ad.impressions)),
            (lbl("clicks"), ui.number_fmt(ad.clicks)),
            (lbl("ctr"), ctr),
        ],
        icon=ui.emoji("ads"),
    )


async def _placement_states(settings: SettingsService) -> dict[str, bool]:
    """Read the on/off state of each registered placement from settings."""
    states: dict[str, bool] = {}
    for opt in PLACEMENT_OPTIONS:
        key = f"ad_placement_{opt.code}_enabled"
        try:
            states[opt.code] = bool(await settings.get(key))
        except SettingNotFoundError:
            states[opt.code] = opt.code in ("post_download", "caption")
    return states


def _placements_text(
    states: dict[str, bool], translate: Translator, locale: str
) -> str:
    lines = [
        ui.header(translate("panel.ads.placements_title", locale), icon=ui.emoji("ads")),
        "",
        translate("panel.ads.placements_subtitle", locale),
    ]
    for opt in PLACEMENT_OPTIONS:
        icon = "✅" if states.get(opt.code) else "❌"
        lines.append(f"  {icon} {translate(opt.label_key, locale)}")
    lines.extend(["", ui.footer()])
    return "\n".join(lines)


def _ads_list_text(rows: Sequence[Any], translate: Translator, locale: str) -> str:
    """Ads section header rendered through ui.py (the ads themselves are buttons)."""
    header = ui.header(translate("panel.ads.list_title", locale), icon=ui.emoji("ads"))
    if not rows:
        return f"{header}\n\n{translate('panel.ads.list_empty', locale)}"
    return "\n".join(
        [
            header,
            "",
            ui.metric(ui.emoji("ads"), translate("panel.ads.count_label", locale), len(rows)),
            "",
            ui.footer(),
        ]
    )


def _language_counts(ads: Sequence[Any]) -> dict[str | None, int]:
    counts: dict[str | None, int] = {}
    for ad in ads:
        lang = getattr(ad, "target_language", None)
        counts[lang] = counts.get(lang, 0) + 1
    return counts


def _ad_stats_text(
    stats: AdDetailedStats,
    bc_sent: int,
    bc_last: datetime.datetime | None,
    translate: Translator,
    locale: str,
) -> str:
    """Per-ad statistics card (Sprint 14, Phase 4.3)."""

    def slbl(name: str) -> str:
        return translate(f"panel.ads.stats.{name}", locale)

    state = translate(
        "panel.ads.state_active" if stats.is_active else "panel.ads.state_disabled",
        locale,
    )
    name_line = stats.internal_name or stats.title
    lines = [
        ui.header(
            f"{name_line} (#{slbl('title_suffix')})",
            icon=ui.emoji("chart"),
        ),
        "",
        ui.metric(ui.emoji("ads"), slbl("state"), state),
        ui.metric(
            ui.emoji("calendar"), slbl("created"), _fmt_dt(stats.created_at)
        ),
        ui.metric(
            ui.emoji("members"), slbl("impressions"), stats.impressions_total
        ),
    ]
    for placement, count in sorted(stats.impressions_by_placement.items()):
        lines.append(
            f"    {ui.emoji('link')} {placement}: {ui.number_fmt(count)}"
        )
    lines.extend(
        [
            ui.metric(ui.emoji("link"), slbl("clicks"), stats.clicks_total),
            ui.metric(ui.emoji("chart"), slbl("ctr"), stats.ctr),
            ui.metric(ui.emoji("fire"), slbl("times_sent"), bc_sent),
            ui.metric(
                ui.emoji("clock"), slbl("last_sent"), _fmt_dt(bc_last)
            ),
            ui.metric(
                ui.emoji("clock"),
                slbl("last_shown"),
                _fmt_dt(stats.last_shown_at),
            ),
        ]
    )
    if stats.buttons:
        lines.append("")
        lines.append(f"<b>{slbl('buttons')}</b>")
        for text, clicks in stats.buttons:
            lines.append(f"  {escape(text)} — {clicks}")
        lines.append(f"<i>{translate('panel.ads.stats.clicks_note', locale)}</i>")
    lines.extend(["", ui.footer()])
    return "\n".join(lines)


async def _overall_stats_text(ads: AdService, translate: Translator, locale: str) -> str:
    """Ad totals rendered as a ui.py metric dashboard (Sprint 13.2 + Phase 4.3 per-ad rows)."""
    all_ads = await ads.list_ads()
    stats = await ads.overall_stats()
    ctr = f"{stats.clicks / stats.impressions * 100:.1f}%" if stats.impressions else "—"

    def lbl(name: str) -> str:
        return translate(f"panel.ads.label.{name}", locale)

    lines = [
        ui.header(translate("panel.ads.stats_title", locale), icon=ui.emoji("chart")),
        "",
        ui.metric(ui.emoji("ads"), lbl("total"), stats.total_ads),
        ui.metric(ui.emoji("active"), lbl("active"), stats.active_ads),
        ui.metric(ui.emoji("members"), lbl("impressions"), stats.impressions),
        ui.metric(ui.emoji("link"), lbl("clicks"), stats.clicks),
        ui.metric(ui.emoji("chart"), lbl("ctr"), ctr),
    ]
    if all_ads:
        lines.append("")
        for ad in all_ads:
            ad_ctr = (
                f"{ad.clicks / ad.impressions * 100:.0f}%"
                if ad.impressions
                else "—"
            )
            state = "✅" if ad.is_active else "⏸"
            lines.append(
                f"{state} #{ad.id} {escape(ad.title)}"
                f" — {ui.number_fmt(ad.impressions)}"
                f" · {ui.number_fmt(ad.clicks)}"
                f" · {ad_ctr}"
            )
    lines.extend(["", ui.footer()])
    return "\n".join(lines)


# Display grouping for the Settings screen (Sprint 13.2): a field index -> group
# code map. The groups follow the existing SETTING_FIELDS order so the text order
# still matches the stepper-button order; a ui.divider + group label is emitted at
# each boundary. Unmapped indices (e.g. a future field) fall into no group and just
# render without a divider, so this never crashes on registry growth.
_SETTINGS_GROUP_BY_INDEX: dict[int, str] = {
    0: "workers",
    1: "limits",
    2: "limits",
    3: "cooldowns",
    4: "cooldowns",
    5: "throughput",
    6: "throughput",
    7: "interface",
    8: "interface",
    9: "interface",
    10: "retention",
    11: "retention",
    12: "retention",
    13: "providers",
    14: "providers",
    15: "providers",
}


async def _settings_text(settings: SettingsService, translate: Translator, locale: str) -> str:
    """Settings screen grouped into labelled sections via the ui.py primitives (13.2)."""
    current = {view.key: view.value for view in await settings.list_all()}
    lines = [
        ui.header(translate("panel.settings.list_header", locale), icon=ui.emoji("settings")),
        "",
        translate("panel.settings.list_subheader", locale),
    ]
    last_group: str | None = None
    for field in SETTING_FIELDS:
        group = _SETTINGS_GROUP_BY_INDEX.get(field.index)
        if group != last_group:
            lines.append(ui.divider())
            if group is not None:
                lines.append(f"  {translate(f'panel.settings.group.{group}', locale)}")
            last_group = group
        label = translate(field.label_key, locale)
        lines.append(ui.metric(ui.emoji("settings"), label, current.get(field.key, "—")))
    lines += ["", ui.footer()]
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


def _job_status_glyph(status: str) -> str:
    """A colour/status glyph for a job row (Sprint 13.2)."""
    lowered = status.lower()
    if lowered in ("completed", "delivered", "done"):
        return ui.emoji("check")
    if "fail" in lowered or lowered in ("error", "cancelled", "canceled"):
        return ui.emoji("dot_red")
    return ui.emoji("hourglass")


async def _jobs_text(
    admin: AdminService,
    *,
    status: str | None = None,
    title_key: str = "panel.jobs.default_title",
    translate: Translator,
    locale: str,
) -> str:
    """Recent / active jobs list rendered through the ui.py design system (Sprint 13.2)."""
    jobs = await admin.list_jobs(limit=_LIST_LIMIT, status=status)
    header = ui.header(translate(title_key, locale), icon=ui.emoji("history"))
    if not jobs:
        return f"{header}\n\n{translate('panel.jobs.empty', locale)}"
    lines = [header, ""]
    for job in jobs:
        lines.append(
            f"  {_job_status_glyph(job.status)} <code>{escape(job.id[:8])}</code> · "
            f"{escape(job.status)} · {escape(job.format)}/{escape(job.quality)}"
        )
    lines += ["", ui.footer()]
    return "\n".join(lines)


async def _errors_text(admin: AdminService, translate: Translator, locale: str) -> str:
    """Recent errors list rendered through the ui.py design system (Sprint 13.2)."""
    errors = await admin.browse_errors(limit=_LIST_LIMIT)
    header = ui.header(translate("panel.errors.title", locale), icon=ui.emoji("warn"))
    if not errors:
        return f"{header}\n\n{translate('panel.errors.empty', locale)}"
    lines = [header, ""]
    for err in errors:
        # Severity at a glance: this screen is a phone-sized triage view, and the whole
        # point of the split is being able to tell a 🔴 outage from a 🔵 unsupported
        # link without reading. Rows predating the 2026071901 migration have no
        # severity and keep the neutral icon.
        icon = _SEVERITY_ICON.get(err.severity or "", ui.emoji("warn"))
        where = f" [{escape(err.platform)}]" if err.platform else ""
        lines.append(
            f"  {icon} <code>{err.created_at:%m-%d %H:%M}</code>{where} · "
            f"{escape(err.error_type)}: {escape(err.message[:60])}"
        )
    lines += ["", ui.footer()]
    return "\n".join(lines)


def _broadcast_text(translate: Translator, locale: str) -> str:
    """Broadcast section screen rendered through the ui.py design system (13.2)."""
    return "\n".join(
        [
            ui.header(translate("panel.broadcast.title", locale), icon=ui.emoji("broadcast")),
            "",
            translate("panel.broadcast.subtitle", locale),
        ]
    )


def _broadcast_list_text(
    broadcasts: list[Any], translate: Translator, locale: str
) -> str:
    hdr = ui.header(translate("panel.broadcast.list_title", locale), icon=ui.emoji("broadcast"))
    if not broadcasts:
        return f"{hdr}\n\n{translate('panel.broadcast.list_empty', locale)}"
    lines: list[str] = [hdr, ""]
    lines.append(
        ui.metric(
            ui.emoji("broadcast"), translate("panel.ads.count_label", locale), len(broadcasts)
        )
    )
    lines += ["", ui.footer()]
    return "\n".join(lines)


def _broadcast_detail_text(
    broadcast: Any, translate: Translator, locale: str
) -> str:
    status = getattr(broadcast, "status", "unknown")
    status_label = {"draft": "📝 Draft", "pending": "⏳ Pending", "completed": "✅ Sent"}.get(
        status, status
    )
    preview = (getattr(broadcast, "message_text", "") or "")[:200].strip() or "—"
    fields = [
        ("Status", status_label),
        ("Language", (getattr(broadcast, "target_language", None) or "—").upper()),
        ("Expected", str(getattr(broadcast, "expected_total", 0))),
    ]
    if status == "completed":
        fields.append(("Sent", str(getattr(broadcast, "total_sent", 0))))
        fields.append(("Failed", str(getattr(broadcast, "total_failed", 0))))
    return "\n".join([
        ui.header(
            translate("panel.broadcast.detail_title", locale, id=broadcast.id),
            icon=ui.emoji("broadcast"),
        ),
        "",
        ui.card("", fields),
        "",
        f"<blockquote>{escape(preview)}</blockquote>",
    ])


async def _queue_text(queue: QueueService, translate: Translator, locale: str) -> str:
    depth, active = await queue.depth(), await queue.active_count()
    return "\n".join(
        [
            ui.header(translate("panel.downloads.title", locale), icon=ui.emoji("download")),
            "",
            ui.metric(ui.emoji("queue"), translate("panel.downloads.depth", locale), depth),
            ui.metric(ui.emoji("active"), translate("panel.downloads.active", locale), active),
            "",
            ui.footer(),
        ]
    )


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
    on = maintenance is not None and maintenance.value.strip().lower() in ("true", "1", "yes", "on")
    return "\n".join(
        [
            ui.header(translate("panel.system.title", locale), icon=ui.emoji("system")),
            "",
            ui.metric(
                ui.status_dot(on),
                translate("panel.system.maintenance", locale),
                translate(f"panel.system.{'on' if on else 'off'}", locale),
            ),
            ui.metric(
                ui.emoji("members"),
                translate("panel.stats.label.members", locale),
                stats.total_users,
            ),
            ui.metric(
                ui.emoji("download"),
                translate("panel.stats.label.downloads", locale),
                stats.total_downloads,
            ),
            ui.metric(
                ui.emoji("queue"),
                translate("panel.stats.label.queue", locale),
                f"{depth} / {active}",
            ),
            "",
            ui.footer(),
        ]
    )
